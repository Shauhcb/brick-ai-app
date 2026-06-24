from flask import Flask, render_template_string, request, redirect, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import requests
from datetime import datetime
import json
import urllib.parse
import re
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'brick_ai_super_secret_key_123')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# Database helper functions
def get_db():
    conn = sqlite3.connect('brick_ai.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        theme TEXT DEFAULT 'light',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS search_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        query TEXT NOT NULL,
        result TEXT,
        mode TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        rating INTEGER,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        response TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized!")

# Initialize database
init_db()

# Get API keys
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# AI Client
gemini_client = None

def init_ai():
    global gemini_client
    if GEMINI_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            gemini_client = genai.GenerativeModel('gemini-1.5-flash')
            print("✅ Gemini AI initialized")
        except Exception as e:
            print(f"⚠️ Gemini error: {e}")

init_ai()

def get_ai_response(prompt):
    """Get AI response with fallback"""
    if gemini_client:
        try:
            response = gemini_client.generate_content(prompt)
            if response and response.text:
                return response.text
        except Exception as e:
            print(f"Gemini error: {e}")
    
    # Simple fallback responses
    prompt_lower = prompt.lower()
    
    if any(word in prompt_lower for word in ['hello', 'hi', 'hey', 'howdy']):
        return "Hello there! 👋 I'm BRICK AI. How can I help you today?"
    
    if 'how are you' in prompt_lower:
        return "I'm doing great! 😊 Thanks for asking!"
    
    if 'help' in prompt_lower:
        return "I can help you with answering questions, searching the web, or just chatting!"
    
    if 'summer' in prompt_lower:
        now = datetime.now()
        month = now.month
        if month in [6, 7, 8]:
            return "Yes! It is currently summer in the Northern Hemisphere. ☀️"
        elif month in [12, 1, 2]:
            return "No, it's currently winter in the Northern Hemisphere. ❄️"
        else:
            return "It's currently spring or autumn. Summer is coming soon! 🌸"
    
    if 'time' in prompt_lower:
        now = datetime.now()
        return f"The current time is {now.strftime('%I:%M %p')} 📅"
    
    if 'bye' in prompt_lower:
        return "Goodbye! 👋 Have a great day!"
    
    return f"🤖 BRICK AI here! I understand you're asking about: '{prompt}'. How can I help you today?"

# Search Functions - Multiple methods
def search_web(query):
    """Search using multiple APIs with fallbacks"""
    results = []
    
    # Method 1: DuckDuckGo API
    try:
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://api.duckduckgo.com/?q={encoded_query}&format=json&no_html=1&skip_disambig=1"
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('AbstractText'):
                results.append({
                    'title': data.get('Heading', query),
                    'summary': data.get('AbstractText', ''),
                    'url': data.get('AbstractURL', '')
                })
            
            if data.get('RelatedTopics'):
                for topic in data['RelatedTopics'][:5]:
                    if 'Text' in topic:
                        text = topic['Text']
                        text = re.sub(r'<[^>]+>', '', text)
                        url_match = re.search(r'https?://[^\s]+', text)
                        url = url_match.group(0) if url_match else ''
                        text = re.sub(r'https?://[^\s]+', '', text).strip()
                        if text and len(text) > 10:
                            results.append({
                                'title': text[:50] + '...' if len(text) > 50 else text,
                                'summary': text[:200],
                                'url': url
                            })
    except Exception as e:
        print(f"DuckDuckGo error: {e}")
    
    # Method 2: If no results, use Wikipedia API as fallback
    if not results:
        try:
            wiki_results = search_wikipedia(query)
            if wiki_results:
                for item in wiki_results[:3]:
                    results.append({
                        'title': item['title'],
                        'summary': item['summary'],
                        'url': item['url']
                    })
        except Exception as e:
            print(f"Wikipedia fallback error: {e}")
    
    # Method 3: If still no results, return example search links
    if not results:
        encoded_query = urllib.parse.quote_plus(query)
        results = [
            {
                'title': f'🔍 Search "{query}" on Google',
                'summary': f'Click to search for "{query}" on Google',
                'url': f'https://www.google.com/search?q={encoded_query}'
            },
            {
                'title': f'📚 Search "{query}" on Wikipedia',
                'summary': f'Click to search for "{query}" on Wikipedia',
                'url': f'https://en.wikipedia.org/wiki/{query.replace(" ", "_")}'
            },
            {
                'title': f'🔎 Search "{query}" on Bing',
                'summary': f'Click to search for "{query}" on Bing',
                'url': f'https://www.bing.com/search?q={encoded_query}'
            }
        ]
    
    return results

def search_wikipedia(query):
    """Search Wikipedia"""
    try:
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={encoded_query}&format=json&srlimit=3"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            results = []
            
            for item in data.get('query', {}).get('search', [])[:3]:
                title = item.get('title')
                if title:
                    summary_url = f"https://en.wikipedia.org/w/api.php?action=query&prop=extracts&exintro&explaintext&titles={urllib.parse.quote_plus(title)}&format=json"
                    summary_response = requests.get(summary_url, timeout=10)
                    summary = ''
                    if summary_response.status_code == 200:
                        summary_data = summary_response.json()
                        pages = summary_data.get('query', {}).get('pages', {})
                        for page_id, page_data in pages.items():
                            if 'extract' in page_data:
                                extract = page_data['extract']
                                summary = extract[:300] + '...' if len(extract) > 300 else extract
                                break
                    
                    if not summary:
                        summary = f"Wikipedia article about {title}"
                    
                    results.append({
                        'title': title,
                        'summary': summary,
                        'url': f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
                    })
            
            return results
        return []
    except Exception as e:
        print(f"Wikipedia error: {e}")
        return []

# Templates (Login & Register unchanged)
LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - BRICK AI 👾</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .login-box {
            background: white;
            padding: 40px;
            border-radius: 15px;
            width: 100%;
            max-width: 400px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
        h1 { text-align: center; margin-bottom: 10px; font-size: 32px; color: #667eea; }
        .subtitle { text-align: center; color: #666; margin-bottom: 30px; }
        .input-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; color: #333; font-weight: 500; }
        input {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
        }
        input:focus { outline: none; border-color: #667eea; }
        .btn {
            width: 100%;
            padding: 14px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
        }
        .btn:hover { background: #5a6fd6; }
        .flash {
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
            text-align: center;
        }
        .flash.error { background: #fee; color: #c00; border: 1px solid #fcc; }
        .flash.success { background: #efe; color: #080; border: 1px solid #cfc; }
        .links { text-align: center; margin-top: 20px; }
        .links a { color: #667eea; text-decoration: none; }
        .links a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="login-box">
        <h1>👾 BRICK AI</h1>
        <p class="subtitle">Your AI-Powered Search Companion</p>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% for category, message in messages %}
                <div class="flash {{ category }}">{{ message }}</div>
            {% endfor %}
        {% endwith %}
        <form method="POST">
            <div class="input-group">
                <label>Email</label>
                <input type="email" name="email" required>
            </div>
            <div class="input-group">
                <label>Password</label>
                <input type="password" name="password" required>
            </div>
            <button type="submit" class="btn">🔐 Login</button>
        </form>
        <div class="links"><a href="/register">Create an Account</a></div>
    </div>
</body>
</html>
'''

REGISTER_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Register - BRICK AI 👾</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .register-box {
            background: white;
            padding: 40px;
            border-radius: 15px;
            width: 100%;
            max-width: 400px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
        h1 { text-align: center; margin-bottom: 10px; font-size: 32px; color: #667eea; }
        .subtitle { text-align: center; color: #666; margin-bottom: 30px; }
        .input-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; color: #333; font-weight: 500; }
        input {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
        }
        input:focus { outline: none; border-color: #667eea; }
        .btn {
            width: 100%;
            padding: 14px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
        }
        .btn:hover { background: #5a6fd6; }
        .flash {
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
            text-align: center;
        }
        .flash.error { background: #fee; color: #c00; border: 1px solid #fcc; }
        .flash.success { background: #efe; color: #080; border: 1px solid #cfc; }
        .links { text-align: center; margin-top: 20px; }
        .links a { color: #667eea; text-decoration: none; }
        .links a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="register-box">
        <h1>👾 BRICK AI</h1>
        <p class="subtitle">Create Your Account</p>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% for category, message in messages %}
                <div class="flash {{ category }}">{{ message }}</div>
            {% endfor %}
        {% endwith %}
        <form method="POST">
            <div class="input-group">
                <label>Username</label>
                <input type="text" name="username" required>
            </div>
            <div class="input-group">
                <label>Email</label>
                <input type="email" name="email" required>
            </div>
            <div class="input-group">
                <label>Password</label>
                <input type="password" name="password" required>
            </div>
            <button type="submit" class="btn">📝 Register</button>
        </form>
        <div class="links"><a href="/login">Already have an account? Login</a></div>
    </div>
</body>
</html>
'''

# Main Chat Template
MAIN_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BRICK AI 👾</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: {% if session.get('theme') == 'dark' %}linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%){% else %}linear-gradient(135deg, #667eea 0%, #764ba2 100%){% endif %};
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: rgba(255,255,255,0.95);
            border-radius: 20px;
            overflow: hidden;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            display: flex;
            flex-direction: column;
            height: 90vh;
        }
        .header {
            background: {% if session.get('theme') == 'dark' %}#1a1a2e{% else %}#667eea{% endif %};
            padding: 15px 25px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
        }
        .header h1 {
            font-size: 24px;
            color: white;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .header-buttons { display: flex; gap: 10px; }
        .btn-icon {
            background: rgba(255,255,255,0.2);
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            text-decoration: none;
            display: inline-block;
            transition: all 0.3s;
        }
        .btn-icon:hover { background: rgba(255,255,255,0.3); transform: translateY(-2px); }
        
        .main-content {
            display: flex;
            flex: 1;
            height: calc(90vh - 70px);
        }
        .sidebar {
            width: 280px;
            background: {% if session.get('theme') == 'dark' %}#16213e{% else %}#f8f9ff{% endif %};
            border-right: 1px solid #e0e0e0;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        .sidebar-header {
            padding: 15px;
            border-bottom: 1px solid #e0e0e0;
        }
        .sidebar-header h3 {
            color: #667eea;
            font-size: 16px;
        }
        .sidebar-search {
            padding: 10px 15px;
            border-bottom: 1px solid #e0e0e0;
        }
        .sidebar-search input {
            width: 100%;
            padding: 8px 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 14px;
            background: white;
        }
        .sidebar-search input:focus { outline: none; border-color: #667eea; }
        .chat-list {
            flex: 1;
            overflow-y: auto;
            padding: 10px;
        }
        .chat-item {
            padding: 12px 15px;
            border-radius: 10px;
            margin-bottom: 8px;
            cursor: pointer;
            transition: all 0.3s;
            background: white;
            border: 1px solid #e8eaff;
        }
        .chat-item:hover {
            background: #e8eaff;
            transform: translateX(5px);
        }
        .chat-item.active {
            background: #667eea;
            border-color: #667eea;
        }
        .chat-item.active h4 { color: white; }
        .chat-item.active p { color: rgba(255,255,255,0.8); }
        .chat-item h4 {
            font-size: 14px;
            color: #333;
            margin-bottom: 4px;
        }
        .chat-item p {
            font-size: 12px;
            color: #999;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .chat-item .time {
            font-size: 10px;
            color: #bbb;
            float: right;
        }
        
        .chat-area {
            flex: 1;
            display: flex;
            flex-direction: column;
            background: {% if session.get('theme') == 'dark' %}#1a1a2e{% else %}#ffffff{% endif %};
        }
        .chat-header {
            padding: 15px 20px;
            background: {% if session.get('theme') == 'dark' %}#16213e{% else %}#f8f9ff{% endif %};
            border-bottom: 1px solid #e0e0e0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .chat-header h3 {
            color: #667eea;
            font-size: 18px;
        }
        .chat-header .clear-chat {
            background: #e74c3c;
            color: white;
            border: none;
            padding: 6px 15px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 12px;
        }
        .chat-header .clear-chat:hover { background: #c0392b; }
        
        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            background: {% if session.get('theme') == 'dark' %}#0f3460{% else %}#f8f9ff{% endif %};
            min-height: 400px;
        }
        .chat-message {
            margin-bottom: 15px;
            padding: 12px 16px;
            border-radius: 12px;
            max-width: 75%;
            animation: fadeIn 0.3s;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .chat-message.user {
            background: #667eea;
            color: white;
            margin-left: auto;
            border-bottom-right-radius: 4px;
        }
        .chat-message.ai {
            background: white;
            color: #333;
            margin-right: auto;
            border-bottom-left-radius: 4px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }
        .chat-message .time {
            font-size: 10px;
            opacity: 0.7;
            margin-top: 5px;
            display: block;
        }
        .chat-message.user .time { color: rgba(255,255,255,0.8); }
        .chat-message.ai .time { color: #999; }
        
        .chat-input-area {
            padding: 15px 20px;
            background: {% if session.get('theme') == 'dark' %}#16213e{% else %}#f8f9ff{% endif %};
            border-top: 1px solid #e0e0e0;
            display: flex;
            gap: 10px;
        }
        .chat-input {
            flex: 1;
            padding: 12px 16px;
            border: 2px solid #e0e0e0;
            border-radius: 25px;
            font-size: 14px;
            background: white;
        }
        .chat-input:focus { outline: none; border-color: #667eea; }
        .chat-send-btn {
            padding: 12px 25px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 25px;
            font-size: 14px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
        }
        .chat-send-btn:hover { background: #5a6fd6; transform: scale(1.02); }
        .chat-send-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        
        .chat-typing {
            display: none;
            padding: 12px 20px;
            color: #667eea;
            font-style: italic;
            font-size: 14px;
        }
        .chat-typing.active { display: block; }
        .chat-typing .blinking-emoji-small {
            display: inline-block;
            animation: blink 0.6s infinite;
            font-size: 18px;
        }
        @keyframes blink {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.2; transform: scale(0.8); }
        }
        
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: #999;
        }
        .empty-state .emoji {
            font-size: 48px;
            display: block;
            margin-bottom: 15px;
        }
        
        .tab-navigation {
            display: none;
        }
        
        @media (max-width: 768px) {
            .sidebar {
                width: 200px;
            }
            .container { height: 95vh; }
            .chat-message { max-width: 90%; }
            .header h1 { font-size: 18px; }
        }
        @media (max-width: 600px) {
            .main-content { flex-direction: column; }
            .sidebar {
                width: 100%;
                height: 200px;
                border-right: none;
                border-bottom: 1px solid #e0e0e0;
            }
            .chat-area { height: calc(100% - 200px); }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>👾 BRICK AI</h1>
            <div class="header-buttons">
                <a href="/search" class="btn-icon">🔍 Search</a>
                <a href="/settings" class="btn-icon">⚙️ Settings</a>
                <button onclick="showFeedback()" class="btn-icon">💬 Feedback</button>
            </div>
        </div>
        
        <div class="main-content">
            <div class="sidebar">
                <div class="sidebar-header">
                    <h3>💬 Chats</h3>
                </div>
                <div class="sidebar-search">
                    <input type="text" id="searchChats" placeholder="Search Chats..." onkeyup="filterChats()">
                </div>
                <div class="chat-list" id="chatList">
                    <div class="chat-item active" onclick="loadChat('main')">
                        <h4>BRICK AI Assistant</h4>
                        <p>Your AI companion</p>
                        <span class="time">Now</span>
                    </div>
                </div>
            </div>
            
            <div class="chat-area">
                <div class="chat-header">
                    <h3 id="chatTitle">💬 BRICK AI Assistant</h3>
                    <button class="clear-chat" onclick="clearChat()">🗑️ Clear Chat</button>
                </div>
                <div class="chat-messages" id="chatMessages">
                    <div class="empty-state">
                        <span class="emoji">👾</span>
                        <p>Start a conversation with BRICK AI</p>
                    </div>
                </div>
                <div class="chat-typing" id="chatTyping">
                    <span class="blinking-emoji-small">👾</span> BRICK AI is thinking...
                </div>
                <div class="chat-input-area">
                    <input type="text" class="chat-input" id="chatInput" placeholder="Type your message..." onkeypress="if(event.key==='Enter') sendMessage()">
                    <button class="chat-send-btn" id="chatSendBtn" onclick="sendMessage()">Send</button>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let currentChat = 'main';
        
        function loadChatHistory() {
            fetch('/get-chat-history')
                .then(response => response.json())
                .then(data => {
                    const container = document.getElementById('chatMessages');
                    container.innerHTML = '';
                    if (data.history && data.history.length > 0) {
                        data.history.forEach(msg => {
                            addMessage('user', msg.message);
                            addMessage('ai', msg.response);
                        });
                    } else {
                        container.innerHTML = `
                            <div class="empty-state">
                                <span class="emoji">👾</span>
                                <p>Start a conversation with BRICK AI</p>
                            </div>
                        `;
                    }
                })
                .catch(() => {
                    const container = document.getElementById('chatMessages');
                    container.innerHTML = `
                        <div class="empty-state">
                            <span class="emoji">👾</span>
                            <p>Start a conversation with BRICK AI</p>
                        </div>
                    `;
                });
        }
        
        function loadChat(chatId) {
            currentChat = chatId;
            document.querySelectorAll('.chat-item').forEach(el => el.classList.remove('active'));
            event.target.closest('.chat-item').classList.add('active');
            loadChatHistory();
        }
        
        function filterChats() {
            const input = document.getElementById('searchChats');
            const filter = input.value.toLowerCase();
            const items = document.querySelectorAll('.chat-item');
            items.forEach(item => {
                const text = item.textContent.toLowerCase();
                item.style.display = text.includes(filter) ? '' : 'none';
            });
        }
        
        function sendMessage() {
            const input = document.getElementById('chatInput');
            const message = input.value.trim();
            if (!message) return;
            
            document.querySelector('.empty-state')?.remove();
            
            addMessage('user', message);
            input.value = '';
            input.disabled = true;
            document.getElementById('chatSendBtn').disabled = true;
            document.getElementById('chatTyping').classList.add('active');
            
            fetch('/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message: message})
            })
            .then(response => response.json())
            .then(data => {
                document.getElementById('chatTyping').classList.remove('active');
                input.disabled = false;
                document.getElementById('chatSendBtn').disabled = false;
                input.focus();
                if (data.response) {
                    addMessage('ai', data.response);
                } else {
                    addMessage('ai', 'Sorry, I had trouble responding. Please try again.');
                }
            })
            .catch(error => {
                document.getElementById('chatTyping').classList.remove('active');
                input.disabled = false;
                document.getElementById('chatSendBtn').disabled = false;
                input.focus();
                addMessage('ai', 'Sorry, there was an error. Please try again.');
            });
        }
        
        function addMessage(type, text) {
            const container = document.getElementById('chatMessages');
            const time = new Date().toLocaleTimeString();
            const div = document.createElement('div');
            div.className = 'chat-message ' + type;
            if (type === 'ai') {
                div.innerHTML = '<strong>👾 BRICK AI</strong><p>' + text.replace(/\\n/g, '<br>') + '</p><span class="time">' + time + '</span>';
            } else {
                div.innerHTML = '<p>' + text.replace(/\\n/g, '<br>') + '</p><span class="time">' + time + '</span>';
            }
            container.appendChild(div);
            container.scrollTop = container.scrollHeight;
        }
        
        function clearChat() {
            if (confirm('Are you sure you want to clear the chat history?')) {
                fetch('/clear-chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'}
                }).then(() => {
                    document.getElementById('chatMessages').innerHTML = `
                        <div class="empty-state">
                            <span class="emoji">👾</span>
                            <p>Chat cleared! Start a new conversation.</p>
                        </div>
                    `;
                });
            }
        }
        
        function showFeedback() {
            const feedback = prompt('We value your feedback! Please share your thoughts:');
            if (feedback) {
                fetch('/submit-feedback', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: feedback})
                }).then(response => {
                    if (response.ok) alert('Thank you for your feedback!');
                });
            }
        }
        
        document.getElementById('chatInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') sendMessage();
        });
        
        window.onload = function() {
            loadChatHistory();
        };
    </script>
</body>
</html>
'''

# Search Page Template
SEARCH_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Search - BRICK AI 👾</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: {% if session.get('theme') == 'dark' %}linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%){% else %}linear-gradient(135deg, #667eea 0%, #764ba2 100%){% endif %};
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1000px; margin: 0 auto; }
        .header {
            background: rgba(255,255,255,0.95);
            padding: 20px 25px;
            border-radius: 15px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
        .header h1 { font-size: 28px; color: #667eea; }
        .header-buttons { display: flex; gap: 10px; flex-wrap: wrap; }
        .btn-icon {
            background: #667eea;
            color: white;
            border: none;
            padding: 10px 18px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            text-decoration: none;
            display: inline-block;
            transition: all 0.3s;
        }
        .btn-icon:hover { background: #5a6fd6; transform: translateY(-2px); }
        .search-box {
            background: rgba(255,255,255,0.95);
            padding: 25px;
            border-radius: 15px;
            margin-bottom: 20px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
        .search-input {
            width: 100%;
            padding: 15px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            font-size: 16px;
            margin-bottom: 15px;
        }
        .search-input:focus { outline: none; border-color: #667eea; }
        .search-mode {
            display: flex;
            gap: 8px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }
        .mode-btn {
            padding: 8px 14px;
            border: 2px solid #667eea;
            background: white;
            color: #667eea;
            border-radius: 8px;
            cursor: pointer;
            font-weight: bold;
            font-size: 13px;
            transition: all 0.3s;
            flex: 1;
            text-align: center;
        }
        .mode-btn.active { background: #667eea; color: white; }
        .mode-btn:hover { background: #667eea; color: white; }
        .search-btn {
            width: 100%;
            padding: 15px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 18px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
        }
        .search-btn:hover { background: #5a6fd6; transform: scale(1.02); }
        .search-btn:disabled { opacity: 0.7; cursor: not-allowed; }
        .loading-container {
            display: none;
            text-align: center;
            padding: 40px;
            background: rgba(255,255,255,0.95);
            border-radius: 15px;
            margin: 20px 0;
        }
        .loading-container.active { display: block; }
        .blinking-emoji {
            font-size: 64px;
            display: inline-block;
            animation: blink 0.8s infinite;
        }
        @keyframes blink {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.2; transform: scale(0.8); }
        }
        .loading-text {
            font-size: 22px;
            color: #667eea;
            margin-top: 15px;
            font-weight: bold;
        }
        .results-container {
            background: rgba(255,255,255,0.95);
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
        .source-section {
            margin-bottom: 25px;
            padding: 20px;
            border-left: 4px solid #667eea;
            background: #f8f9ff;
            border-radius: 8px;
            animation: fadeIn 0.5s;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .source-header {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 15px;
            font-size: 20px;
            font-weight: bold;
            color: #667eea;
        }
        .result-item {
            margin-bottom: 15px;
            padding: 15px;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            animation: fadeIn 0.5s;
        }
        .result-title { font-weight: bold; color: #333; margin-bottom: 8px; }
        .result-summary { color: #666; line-height: 1.6; }
        .result-link { color: #667eea; text-decoration: none; font-size: 14px; display: inline-block; margin-top: 8px; }
        .result-link:hover { text-decoration: underline; }
        .flash-messages { margin-bottom: 20px; }
        .flash {
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 10px;
        }
        .flash.error { background: #fee; color: #c00; border: 1px solid #fcc; }
        .flash.success { background: #efe; color: #080; border: 1px solid #cfc; }
        .history-section {
            margin-top: 20px;
            padding: 20px;
            background: rgba(255,255,255,0.95);
            border-radius: 15px;
        }
        .history-item {
            padding: 12px;
            margin-bottom: 10px;
            background: #f8f9ff;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s;
        }
        .history-item:hover { background: #e8eaff; transform: translateX(5px); }
        .back-btn {
            display: inline-block;
            margin-bottom: 20px;
            color: #667eea;
            text-decoration: none;
            font-weight: bold;
        }
        .back-btn:hover { text-decoration: underline; }
        @media (max-width: 600px) {
            .header { flex-direction: column; gap: 15px; }
            .header-buttons { width: 100%; justify-content: center; }
            .mode-btn { font-size: 11px; padding: 6px 10px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <a href="/dashboard" class="back-btn">← Back to Chats</a>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
            <div class="flash-messages">
                {% for category, message in messages %}
                    <div class="flash {{ category }}">{{ message }}</div>
                {% endfor %}
            </div>
            {% endif %}
        {% endwith %}
        
        <div class="header">
            <h1>🔍 BRICK AI Search</h1>
            <div class="header-buttons">
                <a href="/settings" class="btn-icon">⚙️ Settings</a>
            </div>
        </div>
        
        <div class="search-box">
            <form method="POST" action="/search">
                <input type="text" class="search-input" id="searchQuery" name="query" placeholder="What would you like to search?" value="{{ query if query else '' }}">
                <div class="search-mode">
                    <button type="button" class="mode-btn active" onclick="setMode('all')">🔍 All</button>
                    <button type="button" class="mode-btn" onclick="setMode('google')">🌐 Google</button>
                    <button type="button" class="mode-btn" onclick="setMode('bing')">🔎 Bing</button>
                    <button type="button" class="mode-btn" onclick="setMode('wiki')">📚 Wiki</button>
                    <button type="button" class="mode-btn" onclick="setMode('ai')">🤖 AI</button>
                </div>
                <input type="hidden" name="mode" id="modeInput" value="all">
                <button type="submit" class="search-btn" id="searchBtn">🚀 Search Now</button>
            </form>
        </div>
        
        <div class="loading-container" id="searchLoading">
            <div class="blinking-emoji">👾</div>
            <div class="loading-text">BRICK AI is thinking...</div>
        </div>
        
        {% if result %}
        <div class="results-container">{{ result|safe }}</div>
        {% endif %}
        
        {% if history %}
        <div class="history-section">
            <h2 style="color: #667eea;">📜 Recent Searches</h2>
            {% for item in history %}
            <div class="history-item" onclick="loadSearch('{{ item.query }}')">
                <strong>{{ item.query }}</strong><br><small>{{ item.timestamp }}</small>
            </div>
            {% endfor %}
        </div>
        {% endif %}
    </div>
    
    <script>
        let currentMode = 'all';
        
        function setMode(mode) {
            currentMode = mode;
            document.querySelectorAll('.mode-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            document.getElementById('modeInput').value = mode;
        }
        
        function loadSearch(query) {
            document.getElementById('searchQuery').value = query;
            document.querySelector('form').submit();
        }
        
        document.getElementById('searchQuery').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                document.querySelector('form').submit();
            }
        });
    </script>
</body>
</html>
'''

SETTINGS_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Settings - BRICK AI 👾</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: {% if session.get('theme') == 'dark' %}linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%){% else %}linear-gradient(135deg, #667eea 0%, #764ba2 100%){% endif %};
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 700px; margin: 0 auto; }
        .settings-card {
            background: rgba(255,255,255,0.95);
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
        h1 { text-align: center; margin-bottom: 25px; color: #667eea; font-size: 28px; }
        .setting-item {
            margin-bottom: 25px;
            padding-bottom: 20px;
            border-bottom: 1px solid #e0e0e0;
        }
        .setting-item:last-child { border-bottom: none; }
        .setting-label { font-weight: bold; color: #333; margin-bottom: 10px; display: block; font-size: 16px; }
        .theme-options { display: flex; gap: 15px; }
        .theme-btn {
            flex: 1;
            padding: 15px;
            border: 2px solid #e0e0e0;
            background: white;
            border-radius: 10px;
            cursor: pointer;
            font-size: 16px;
            transition: all 0.3s;
        }
        .theme-btn.active { border-color: #667eea; background: #f8f9ff; }
        .theme-btn:hover { border-color: #667eea; transform: translateY(-2px); }
        .toggle-container {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 10px 0;
        }
        .toggle {
            position: relative;
            width: 50px;
            height: 28px;
            background: #ccc;
            border-radius: 14px;
            cursor: pointer;
            transition: all 0.3s;
        }
        .toggle.active { background: #667eea; }
        .toggle .slider {
            position: absolute;
            top: 3px;
            left: 3px;
            width: 22px;
            height: 22px;
            background: white;
            border-radius: 50%;
            transition: all 0.3s;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }
        .toggle.active .slider { left: 25px; }
        .logout-btn {
            width: 100%;
            padding: 15px;
            background: #e74c3c;
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            text-decoration: none;
            display: inline-block;
            text-align: center;
            transition: all 0.3s;
        }
        .logout-btn:hover { background: #c0392b; transform: translateY(-2px); }
        .back-btn {
            display: inline-block;
            margin-bottom: 20px;
            color: #667eea;
            text-decoration: none;
            font-weight: bold;
            font-size: 16px;
        }
        .back-btn:hover { text-decoration: underline; }
        .user-info {
            background: #f8f9ff;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .user-info p { margin: 5px 0; color: #333; }
        .user-info strong { color: #667eea; }
        .stats-grid {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 10px;
        }
        .stat-box {
            background: #f8f9ff;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }
        .stat-box .number { font-size: 24px; font-weight: bold; color: #667eea; }
        .stat-box .label { color: #666; font-size: 13px; margin-top: 5px; }
        .flash-messages { margin-bottom: 20px; }
        .flash {
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 10px;
        }
        .flash.error { background: #fee; color: #c00; border: 1px solid #fcc; }
        .flash.success { background: #efe; color: #080; border: 1px solid #cfc; }
        .action-btn {
            width: 100%;
            padding: 12px;
            margin-bottom: 10px;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
        }
        .action-btn:hover { transform: translateY(-2px); }
        .btn-warning { background: #f39c12; color: white; }
        .btn-warning:hover { background: #e67e22; }
        .btn-info { background: #3498db; color: white; }
        .btn-info:hover { background: #2980b9; }
        @media (max-width: 600px) {
            .stats-grid { grid-template-columns: 1fr; }
            .theme-options { flex-direction: column; }
        }
    </style>
</head>
<body>
    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
            <div class="flash-messages">
                {% for category, message in messages %}
                    <div class="flash {{ category }}">{{ message }}</div>
                {% endfor %}
            </div>
            {% endif %}
        {% endwith %}
        
        <a href="/dashboard" class="back-btn">← Back to Chats</a>
        <div class="settings-card">
            <h1>⚙️ BRICK AI Settings</h1>
            
            <div class="user-info">
                <p><strong>👤 Username:</strong> {{ session.get('username') }}</p>
                <p><strong>📧 Email:</strong> {{ session.get('user_email', 'N/A') }}</p>
                <p><strong>📅 Member Since:</strong> {{ created_at }}</p>
            </div>
            
            <div class="setting-item">
                <span class="setting-label">🎨 App Theme</span>
                <div class="theme-options">
                    <button class="theme-btn {% if session.get('theme') != 'dark' %}active{% endif %}" onclick="setTheme('light')">☀️ Light</button>
                    <button class="theme-btn {% if session.get('theme') == 'dark' %}active{% endif %}" onclick="setTheme('dark')">🌙 Dark</button>
                </div>
            </div>
            
            <div class="setting-item">
                <span class="setting-label">💬 Chat Settings</span>
                <div class="toggle-container">
                    <span>Auto-save chat history</span>
                    <div class="toggle active" onclick="toggleSetting('auto_save')">
                        <div class="slider"></div>
                    </div>
                </div>
                <div class="toggle-container">
                    <span>Show timestamps</span>
                    <div class="toggle active" onclick="toggleSetting('timestamps')">
                        <div class="slider"></div>
                    </div>
                </div>
            </div>
            
            <div class="setting-item">
                <span class="setting-label">📊 Account Statistics</span>
                <div class="stats-grid">
                    <div class="stat-box">
                        <div class="number">{{ search_count }}</div>
                        <div class="label">Searches</div>
                    </div>
                    <div class="stat-box">
                        <div class="number">{{ chat_count }}</div>
                        <div class="label">Chats</div>
                    </div>
                    <div class="stat-box">
                        <div class="number">{{ feedback_count }}</div>
                        <div class="label">Feedback</div>
                    </div>
                </div>
            </div>
            
            <div class="setting-item">
                <span class="setting-label">📝 Data Management</span>
                <button class="action-btn btn-warning" onclick="clearHistory()">🗑️ Clear Search History</button>
                <button class="action-btn btn-info" onclick="exportData()">📤 Export My Data</button>
            </div>
            
            <div class="setting-item">
                <span class="setting-label">🔐 Account</span>
                <a href="/logout" class="logout-btn">🚪 Logout</a>
            </div>
        </div>
    </div>
    <script>
        function setTheme(theme) {
            fetch('/set-theme', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({theme: theme})
            }).then(() => location.reload());
        }
        
        function toggleSetting(setting) {
            const toggle = event.target.closest('.toggle');
            toggle.classList.toggle('active');
            fetch('/update-setting', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({setting: setting, value: toggle.classList.contains('active')})
            });
        }
        
        function clearHistory() {
            if (confirm('Are you sure you want to clear all your search history?')) {
                fetch('/clear-history', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'}
                }).then(() => {
                    alert('Search history cleared!');
                    location.reload();
                });
            }
        }
        
        function exportData() {
            window.location.href = '/export-data';
        }
    </script>
</body>
</html>
'''

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect('/dashboard')
    return redirect('/login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect('/dashboard')
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = c.fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['user_email'] = user['email']
            session['theme'] = user['theme'] if user['theme'] else 'light'
            flash('Logged in successfully!', 'success')
            return redirect('/dashboard')
        else:
            flash('Invalid email or password!', 'error')
    
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect('/dashboard')
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        conn = get_db()
        c = conn.cursor()
        
        c.execute('SELECT * FROM users WHERE email = ?', (email,))
        if c.fetchone():
            conn.close()
            flash('Email already registered!', 'error')
            return render_template_string(REGISTER_TEMPLATE)
        
        c.execute('SELECT * FROM users WHERE username = ?', (username,))
        if c.fetchone():
            conn.close()
            flash('Username already taken!', 'error')
            return render_template_string(REGISTER_TEMPLATE)
        
        hashed_password = generate_password_hash(password)
        c.execute('INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
                 (username, email, hashed_password))
        conn.commit()
        conn.close()
        
        flash('Account created! Please login.', 'success')
        return redirect('/login')
    
    return render_template_string(REGISTER_TEMPLATE)

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Please login first.', 'error')
        return redirect('/login')
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
    user = c.fetchone()
    
    if not user:
        conn.close()
        session.clear()
        flash('User not found. Please login again.', 'error')
        return redirect('/login')
    
    conn.close()
    return render_template_string(MAIN_TEMPLATE)

@app.route('/search', methods=['GET'])
def search_page():
    if 'user_id' not in session:
        flash('Please login first.', 'error')
        return redirect('/login')
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM search_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10', (session['user_id'],))
    history = c.fetchall()
    conn.close()
    
    return render_template_string(SEARCH_TEMPLATE, result='', query='', history=history)

@app.route('/search', methods=['POST'])
def search():
    if 'user_id' not in session:
        flash('Please login first.', 'error')
        return redirect('/login')
    
    query = request.form.get('query', '')
    mode = request.form.get('mode', 'all')
    
    if not query:
        flash('Please enter a search query.', 'error')
        return redirect('/search')
    
    html_parts = []
    
    # Web Search (Google/Bing/All)
    if mode in ['all', 'google', 'bing']:
        results = search_web(query)
        if results:
            source_name = 'Google' if mode == 'google' else 'Bing' if mode == 'bing' else 'Web'
            icon = '🌐' if mode == 'google' else '🔎' if mode == 'bing' else '🔍'
            html_parts.append('<div class="source-section">')
            html_parts.append(f'<div class="source-header"><span class="source-icon">{icon}</span> {source_name} Results</div>')
            for item in results[:5]:
                title = item.get('title', 'Result')
                summary = item.get('summary', '')
                url = item.get('url', '#')
                if url:
                    html_parts.append(f'''
                    <div class="result-item">
                        <div class="result-title">{title}</div>
                        <div class="result-summary">{summary[:200]}</div>
                        <a href="{url}" target="_blank" class="result-link">🔗 Visit Link</a>
                    </div>
                    ''')
            html_parts.append('</div>')
        else:
            source_name = 'Google' if mode == 'google' else 'Bing' if mode == 'bing' else 'Web'
            icon = '🌐' if mode == 'google' else '🔎' if mode == 'bing' else '🔍'
            html_parts.append(f'''
            <div class="source-section">
                <div class="source-header"><span class="source-icon">{icon}</span> {source_name}</div>
                <div class="result-item">No results found for "{query}". Try a different search.</div>
            </div>
            ''')
    
    # Wikipedia Search
    if mode in ['all', 'wiki']:
        wiki_results = search_wikipedia(query)
        if wiki_results:
            html_parts.append('<div class="source-section">')
            html_parts.append('<div class="source-header"><span class="source-icon">📚</span> Wikipedia</div>')
            for item in wiki_results:
                html_parts.append(f'''
                <div class="result-item">
                    <div class="result-title">{item['title']}</div>
                    <div class="result-summary">{item['summary']}</div>
                    <a href="{item['url']}" target="_blank" class="result-link">📖 Read More</a>
                </div>
                ''')
            html_parts.append('</div>')
        else:
            html_parts.append(f'''
            <div class="source-section">
                <div class="source-header"><span class="source-icon">📚</span> Wikipedia</div>
                <div class="result-item">No Wikipedia articles found for "{query}".</div>
            </div>
            ''')
    
    # AI Search
    if mode in ['all', 'ai']:
        ai_result = get_ai_response(f"Provide a comprehensive answer to: {query}")
        if ai_result:
            html_parts.append('<div class="source-section">')
            html_parts.append('<div class="source-header"><span class="source-icon">🤖</span> AI Smart Summary</div>')
            html_parts.append(f'<div class="result-item"><div class="result-summary">{ai_result}</div></div>')
            html_parts.append('</div>')
        else:
            html_parts.append(f'''
            <div class="source-section">
                <div class="source-header"><span class="source-icon">🤖</span> AI Smart Summary</div>
                <div class="result-item">AI search is currently unavailable.</div>
            </div>
            ''')
    
    result_html = ''.join(html_parts) if html_parts else f'<p style="color:#666;text-align:center;padding:20px;">No results found for "{query}".</p>'
    
    # Save to history
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT INTO search_history (user_id, query, result, mode) VALUES (?, ?, ?, ?)',
             (session['user_id'], query, result_html[:500], mode))
    conn.commit()
    conn.close()
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM search_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10', (session['user_id'],))
    history = c.fetchall()
    conn.close()
    
    return render_template_string(SEARCH_TEMPLATE, result=result_html, query=query, history=history)

@app.route('/chat', methods=['POST'])
def chat():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    data = request.get_json()
    message = data.get('message', '')
    
    if not message:
        return jsonify({'error': 'No message provided'}), 400
    
    response = get_ai_response(message)
    
    # Save chat to database
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT INTO chat_messages (user_id, message, response) VALUES (?, ?, ?)',
             (session['user_id'], message, response))
    conn.commit()
    conn.close()
    
    return jsonify({'response': response})

@app.route('/get-chat-history', methods=['GET'])
def get_chat_history():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT message, response, timestamp FROM chat_messages WHERE user_id = ? ORDER BY timestamp ASC', (session['user_id'],))
    messages = c.fetchall()
    conn.close()
    
    history = []
    for msg in messages:
        history.append({
            'message': msg['message'],
            'response': msg['response'],
            'timestamp': msg['timestamp']
        })
    
    return jsonify({'history': history})

@app.route('/clear-chat', methods=['POST'])
def clear_chat():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM chat_messages WHERE user_id = ?', (session['user_id'],))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/settings')
def settings():
    if 'user_id' not in session:
        flash('Please login first.', 'error')
        return redirect('/login')
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
    user = c.fetchone()
    
    if not user:
        conn.close()
        session.clear()
        return redirect('/login')
    
    search_count = c.execute('SELECT COUNT(*) FROM search_history WHERE user_id = ?', (session['user_id'],)).fetchone()[0]
    chat_count = c.execute('SELECT COUNT(*) FROM chat_messages WHERE user_id = ?', (session['user_id'],)).fetchone()[0]
    feedback_count = c.execute('SELECT COUNT(*) FROM feedback WHERE user_id = ?', (session['user_id'],)).fetchone()[0]
    conn.close()
    
    return render_template_string(SETTINGS_TEMPLATE, 
                                 user=user, 
                                 search_count=search_count,
                                 chat_count=chat_count,
                                 feedback_count=feedback_count,
                                 created_at=user['created_at'])

@app.route('/set-theme', methods=['POST'])
def set_theme():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    data = request.get_json()
    theme = data.get('theme', 'light')
    
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE users SET theme = ? WHERE id = ?', (theme, session['user_id']))
    conn.commit()
    conn.close()
    
    session['theme'] = theme
    return jsonify({'success': True})

@app.route('/update-setting', methods=['POST'])
def update_setting():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    data = request.get_json()
    setting = data.get('setting')
    value = data.get('value')
    
    session[setting] = value
    return jsonify({'success': True})

@app.route('/clear-history', methods=['POST'])
def clear_history():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM search_history WHERE user_id = ?', (session['user_id'],))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/export-data', methods=['GET'])
def export_data():
    if 'user_id' not in session:
        flash('Please login first.', 'error')
        return redirect('/login')
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
    user = c.fetchone()
    
    c.execute('SELECT * FROM search_history WHERE user_id = ?', (session['user_id'],))
    searches = c.fetchall()
    
    c.execute('SELECT * FROM chat_messages WHERE user_id = ?', (session['user_id'],))
    chats = c.fetchall()
    
    c.execute('SELECT * FROM feedback WHERE user_id = ?', (session['user_id'],))
    feedbacks = c.fetchall()
    conn.close()
    
    export = {
        'user': dict(user),
        'searches': [dict(s) for s in searches],
        'chats': [dict(c) for c in chats],
        'feedback': [dict(f) for f in feedbacks],
        'exported_at': datetime.now().isoformat()
    }
    
    return jsonify(export)

@app.route('/submit-feedback', methods=['POST'])
def submit_feedback():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    data = request.get_json()
    message = data.get('message', '')
    
    if message:
        conn = get_db()
        c = conn.cursor()
        c.execute('INSERT INTO feedback (user_id, message) VALUES (?, ?)', (session['user_id'], message))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    
    return jsonify({'error': 'No message provided'}), 400

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect('/login')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)