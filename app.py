from flask import Flask, render_template_string, request, redirect, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import requests
from datetime import datetime
import json
import urllib.parse
import re

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
    return get_simple_response(prompt)

def get_simple_response(prompt):
    """Simple rule-based responses when AI is unavailable"""
    prompt_lower = prompt.lower()
    
    greetings = ['hello', 'hi', 'hey', 'howdy', 'greetings']
    if any(word in prompt_lower for word in greetings):
        return "Hello there! 👋 I'm BRICK AI. How can I help you today?"
    
    if 'how are you' in prompt_lower:
        return "I'm doing great! 😊 Thanks for asking. What can I assist you with?"
    
    if 'help' in prompt_lower:
        return "I can help you with:\n• Answering questions\n• Searching the web\n• Chatting about various topics\n• Providing information\n\nWhat would you like to know?"
    
    if 'thank' in prompt_lower:
        return "You're welcome! 😊 Is there anything else I can help with?"
    
    if 'bye' in prompt_lower or 'goodbye' in prompt_lower:
        return "Goodbye! 👋 Feel free to come back anytime. Have a great day!"
    
    if 'weather' in prompt_lower:
        return "I don't have access to real-time weather data, but I recommend checking weather.com or your favorite weather app! 🌤️"
    
    if 'time' in prompt_lower:
        now = datetime.now()
        return f"The current time is {now.strftime('%I:%M %p')} on {now.strftime('%B %d, %Y')} 📅"
    
    # Default response
    return f"""🤖 BRICK AI here!

I understand you're asking about: "{prompt}"

I'm here to help! You can:
• Ask me questions
• Use the Search tab for web results
• Chat with me about anything

What else would you like to know?"""

# Search Functions - Using direct API calls
def search_google(query):
    """Search Google using a free API"""
    try:
        # Using a free Google search API (serpapi or custom search)
        # For now, we'll simulate results with a simple web search
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://api.duckduckgo.com/?q={encoded_query}&format=json"
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            results = []
            # Get related topics
            if data.get('RelatedTopics'):
                for topic in data['RelatedTopics'][:5]:
                    if 'Text' in topic:
                        text = topic['Text']
                        # Extract URL if present
                        if 'FirstURL' in topic:
                            results.append(topic['FirstURL'])
                        else:
                            # Extract URL from text
                            url_match = re.search(r'https?://[^\s]+', text)
                            if url_match:
                                results.append(url_match.group(0))
            
            # If no results, add some example results
            if not results:
                results = [
                    f"https://www.google.com/search?q={encoded_query}",
                    f"https://en.wikipedia.org/wiki/{query.replace(' ', '_')}",
                    f"https://www.bing.com/search?q={encoded_query}"
                ]
            return results[:5]
        return []
    except Exception as e:
        print(f"Google search error: {e}")
        return []

def search_bing(query):
    """Search Bing using a free API"""
    try:
        encoded_query = urllib.parse.quote_plus(query)
        # Using DuckDuckGo as fallback for Bing-like results
        url = f"https://api.duckduckgo.com/?q={encoded_query}&format=json"
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            results = []
            if data.get('RelatedTopics'):
                for topic in data['RelatedTopics'][:3]:
                    if 'Text' in topic and 'FirstURL' in topic:
                        results.append(topic['FirstURL'])
            if not results:
                results = [
                    f"https://www.bing.com/search?q={encoded_query}",
                    f"https://en.wikipedia.org/wiki/{query.replace(' ', '_')}"
                ]
            return results[:3]
        return []
    except Exception as e:
        print(f"Bing search error: {e}")
        return []

def search_wikipedia(query):
    """Search Wikipedia using the official API"""
    try:
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={encoded_query}&format=json"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            results = []
            for item in data.get('query', {}).get('search', [])[:3]:
                title = item.get('title')
                if title:
                    # Get summary for each result
                    summary_url = f"https://en.wikipedia.org/w/api.php?action=query&prop=extracts&exintro&explaintext&titles={urllib.parse.quote_plus(title)}&format=json"
                    summary_response = requests.get(summary_url, timeout=10)
                    if summary_response.status_code == 200:
                        summary_data = summary_response.json()
                        pages = summary_data.get('query', {}).get('pages', {})
                        for page_id, page_data in pages.items():
                            if 'extract' in page_data:
                                summary = page_data['extract'][:300] + "..."
                                results.append({
                                    'title': title,
                                    'summary': summary,
                                    'url': f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
                                })
                                break
                    else:
                        results.append({
                            'title': title,
                            'summary': f"Wikipedia article about {title}",
                            'url': f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
                        })
            return results
        return []
    except Exception as e:
        print(f"Wikipedia search error: {e}")
        return []

# Templates
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
        .header h1 { font-size: 32px; color: #667eea; }
        .header-buttons { display: flex; gap: 10px; flex-wrap: wrap; }
        .btn-icon {
            background: #667eea;
            color: white;
            border: none;
            padding: 10px 18px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 15px;
            text-decoration: none;
            display: inline-block;
            transition: all 0.3s;
        }
        .btn-icon:hover { background: #5a6fd6; transform: translateY(-2px); }
        .tab-navigation { display: flex; gap: 10px; margin-bottom: 20px; }
        .tab-btn {
            padding: 12px 25px;
            background: rgba(255,255,255,0.9);
            border: none;
            border-radius: 10px;
            cursor: pointer;
            font-size: 16px;
            font-weight: bold;
            color: #667eea;
            transition: all 0.3s;
            flex: 1;
        }
        .tab-btn:hover { background: white; transform: translateY(-2px); }
        .tab-btn.active { background: #667eea; color: white; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
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
        .chat-container {
            background: rgba(255,255,255,0.95);
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            height: 600px;
            display: flex;
            flex-direction: column;
        }
        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 10px;
            margin-bottom: 15px;
            background: #f8f9ff;
            border-radius: 10px;
        }
        .chat-message {
            margin-bottom: 15px;
            padding: 12px 16px;
            border-radius: 12px;
            max-width: 80%;
        }
        .chat-message.user { background: #667eea; color: white; margin-left: auto; }
        .chat-message.ai { background: white; color: #333; margin-right: auto; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }
        .chat-message .time { font-size: 11px; opacity: 0.7; margin-top: 5px; display: block; }
        .chat-input-area { display: flex; gap: 10px; }
        .chat-input {
            flex: 1;
            padding: 12px 16px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            font-size: 15px;
        }
        .chat-input:focus { outline: none; border-color: #667eea; }
        .chat-send-btn {
            padding: 12px 25px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 15px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
        }
        .chat-send-btn:hover { background: #5a6fd6; transform: scale(1.02); }
        .chat-send-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .chat-typing {
            display: none;
            padding: 12px;
            color: #667eea;
            font-style: italic;
            font-size: 16px;
        }
        .chat-typing.active { display: block; }
        .chat-typing .blinking-emoji-small {
            display: inline-block;
            animation: blink 0.6s infinite;
            font-size: 22px;
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
        }
        .history-item:hover { background: #e8eaff; }
        @media (max-width: 600px) {
            .header { flex-direction: column; gap: 15px; }
            .header-buttons { width: 100%; justify-content: center; }
            .mode-btn { font-size: 11px; padding: 6px 10px; }
            .tab-btn { font-size: 14px; padding: 10px 15px; }
            .chat-container { height: 500px; }
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
        
        <div class="header">
            <h1>👾 BRICK AI</h1>
            <div class="header-buttons">
                <a href="/settings" class="btn-icon">⚙️ Settings</a>
                <button onclick="showFeedback()" class="btn-icon">💬 Feedback</button>
            </div>
        </div>
        
        <div class="tab-navigation">
            <button class="tab-btn active" onclick="switchTab('search')">🔍 Search</button>
            <button class="tab-btn" onclick="switchTab('chat')">💬 Chat</button>
        </div>
        
        <div id="searchTab" class="tab-content active">
            <div class="search-box">
                <input type="text" class="search-input" id="searchQuery" placeholder="What would you like to search?" value="{{ query if query else '' }}">
                <div class="search-mode">
                    <button class="mode-btn active" onclick="setMode('all')">🔍 All</button>
                    <button class="mode-btn" onclick="setMode('google')">🌐 Google</button>
                    <button class="mode-btn" onclick="setMode('bing')">🔎 Bing</button>
                    <button class="mode-btn" onclick="setMode('wiki')">📚 Wiki</button>
                    <button class="mode-btn" onclick="setMode('ai')">🤖 AI</button>
                </div>
                <button class="search-btn" id="searchBtn" onclick="performSearch()">🚀 Search Now</button>
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
        
        <div id="chatTab" class="tab-content">
            <div class="chat-container">
                <div class="chat-messages" id="chatMessages">
                    <div class="chat-message ai">
                        <strong>👾 BRICK AI</strong>
                        <p>Hello! I'm BRICK AI, your friendly assistant. Ask me anything! 😊</p>
                        <span class="time">Just now</span>
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
        let currentMode = 'all';
        
        function switchTab(tab) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            if (tab === 'search') {
                document.getElementById('searchTab').classList.add('active');
            } else {
                document.getElementById('chatTab').classList.add('active');
            }
            event.target.classList.add('active');
        }
        
        function setMode(mode) {
            currentMode = mode;
            document.querySelectorAll('.mode-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
        }
        
        function performSearch() {
            const query = document.getElementById('searchQuery').value;
            if (!query.trim()) { alert('Please enter a search query'); return; }
            
            const loading = document.getElementById('searchLoading');
            const searchBtn = document.getElementById('searchBtn');
            loading.classList.add('active');
            searchBtn.disabled = true;
            searchBtn.textContent = '⏳ Searching...';
            
            window.location.href = '/search?query=' + encodeURIComponent(query) + '&mode=' + currentMode;
        }
        
        function loadSearch(query) {
            document.getElementById('searchQuery').value = query;
            performSearch();
        }
        
        function sendMessage() {
            const input = document.getElementById('chatInput');
            const message = input.value.trim();
            if (!message) return;
            
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
        document.getElementById('searchQuery').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') performSearch();
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
        .container { max-width: 600px; margin: 0 auto; }
        .settings-card {
            background: rgba(255,255,255,0.95);
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
        h1 { text-align: center; margin-bottom: 25px; color: #667eea; }
        .setting-item {
            margin-bottom: 25px;
            padding-bottom: 20px;
            border-bottom: 1px solid #e0e0e0;
        }
        .setting-item:last-child { border-bottom: none; }
        .setting-label { font-weight: bold; color: #333; margin-bottom: 10px; display: block; }
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
        .theme-btn:hover { border-color: #667eea; }
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
        }
        .logout-btn:hover { background: #c0392b; }
        .back-btn {
            display: inline-block;
            margin-bottom: 20px;
            color: #667eea;
            text-decoration: none;
            font-weight: bold;
        }
        .back-btn:hover { text-decoration: underline; }
        .user-info {
            background: #f8f9ff;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .flash-messages { margin-bottom: 20px; }
        .flash {
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 10px;
        }
        .flash.error { background: #fee; color: #c00; border: 1px solid #fcc; }
        .flash.success { background: #efe; color: #080; border: 1px solid #cfc; }
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
        
        <a href="/dashboard" class="back-btn">← Back to Home</a>
        <div class="settings-card">
            <h1>⚙️ BRICK AI Settings</h1>
            <div class="user-info">
                <strong>👤 Logged in as:</strong> {{ session.get('username') }}<br>
                <strong>📧 Email:</strong> {{ session.get('user_email', 'N/A') }}
            </div>
            <div class="setting-item">
                <span class="setting-label">🎨 Theme</span>
                <div class="theme-options">
                    <button class="theme-btn {% if session.get('theme') != 'dark' %}active{% endif %}" onclick="setTheme('light')">☀️ Light</button>
                    <button class="theme-btn {% if session.get('theme') == 'dark' %}active{% endif %}" onclick="setTheme('dark')">🌙 Dark</button>
                </div>
            </div>
            <div class="setting-item">
                <span class="setting-label">📊 Stats</span>
                <p>Total Searches: {{ search_count }}</p>
                <p>Member Since: {{ created_at }}</p>
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
    
    c.execute('SELECT * FROM search_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10', (session['user_id'],))
    history = c.fetchall()
    conn.close()
    
    return render_template_string(MAIN_TEMPLATE, result='', query='', history=history)

@app.route('/search', methods=['GET'])
def search():
    if 'user_id' not in session:
        flash('Please login first.', 'error')
        return redirect('/login')
    
    query = request.args.get('query', '')
    mode = request.args.get('mode', 'all')
    
    if not query:
        flash('Please enter a search query.', 'error')
        return redirect('/dashboard')
    
    html_parts = []
    
    # Google Search
    if mode in ['all', 'google']:
        google_results = search_google(query)
        if google_results:
            html_parts.append('<div class="source-section">')
            html_parts.append('<div class="source-header"><span class="source-icon">🌐</span> Google Search</div>')
            for i, url in enumerate(google_results[:5], 1):
                html_parts.append(f'''
                <div class="result-item">
                    <div class="result-title">Result {i}</div>
                    <a href="{url}" target="_blank" class="result-link">🔗 {url[:80]}...</a>
                </div>
                ''')
            html_parts.append('</div>')
        else:
            html_parts.append(f'''
            <div class="source-section">
                <div class="source-header"><span class="source-icon">🌐</span> Google Search</div>
                <div class="result-item">No Google results found for "{query}".</div>
            </div>
            ''')
    
    # Bing Search
    if mode in ['all', 'bing']:
        bing_results = search_bing(query)
        if bing_results:
            html_parts.append('<div class="source-section">')
            html_parts.append('<div class="source-header"><span class="source-icon">🔎</span> Bing Search</div>')
            for i, url in enumerate(bing_results[:3], 1):
                html_parts.append(f'''
                <div class="result-item">
                    <div class="result-title">Result {i}</div>
                    <a href="{url}" target="_blank" class="result-link">🔗 {url[:80]}...</a>
                </div>
                ''')
            html_parts.append('</div>')
        else:
            html_parts.append(f'''
            <div class="source-section">
                <div class="source-header"><span class="source-icon">🔎</span> Bing Search</div>
                <div class="result-item">No Bing results found for "{query}".</div>
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
    
    return render_template_string(MAIN_TEMPLATE, result=result_html, query=query, history=history)

@app.route('/chat', methods=['POST'])
def chat():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    data = request.get_json()
    message = data.get('message', '')
    
    if not message:
        return jsonify({'error': 'No message provided'}), 400
    
    response = get_ai_response(f"You are BRICK AI, a friendly assistant. Respond to: {message}")
    
    # Save chat to database
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT INTO chat_messages (user_id, message, response) VALUES (?, ?, ?)',
             (session['user_id'], message, response))
    conn.commit()
    conn.close()
    
    return jsonify({'response': response})

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
    conn.close()
    
    return render_template_string(SETTINGS_TEMPLATE, user=user, search_count=search_count, 
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

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect('/login')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)