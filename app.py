from flask import Flask, render_template_string, request, redirect, session, flash, jsonify, Response
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import requests
from datetime import datetime
import json
import urllib.parse
import html
import time
import secrets

app = Flask(__name__)

# 🔒 SECURE SECRET KEY FIX
secret_key = os.environ.get('SECRET_KEY')
if not secret_key:
    secret_key = secrets.token_hex(32)
    print("⚠️ WARNING: Using randomly generated SECRET_KEY. Set SECRET_KEY env var for production!")
app.config['SECRET_KEY'] = secret_key

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

# Try importing optional packages
try:
    import wikipedia
    print("✅ Wikipedia imported")
except ImportError:
    wikipedia = None
    print("⚠️ Wikipedia not available")

try:
    from googlesearch import search as google_search
    print("✅ Google search imported")
except ImportError:
    google_search = None
    print("⚠️ Google search not available")

# Get API keys
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
HUGGINGFACE_API_KEY = os.environ.get("HUGGINGFACE_API_KEY", "")

# AI Clients
gemini_client = None
huggingface_client = None

def init_ai_clients():
    global gemini_client, huggingface_client    
    # Initialize Gemini
    if GEMINI_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            gemini_client = genai.GenerativeModel('gemini-1.5-flash')
            print("✅ Gemini AI initialized")
        except Exception as e:
            print(f"⚠️ Gemini init error: {e}")
    
    # Initialize HuggingFace (optional)
    if HUGGINGFACE_API_KEY:
        huggingface_client = HUGGINGFACE_API_KEY
        print("✅ HuggingFace API configured")

init_ai_clients()

def query_ai(prompt, max_retries=2):
    """Query AI with fallback: Gemini -> HuggingFace -> Simple Bot"""
    
    # Try Gemini first
    if gemini_client:
        try:
            response = gemini_client.generate_content(prompt)
            if response and response.text:
                return response.text
        except Exception as e:
            print(f"Gemini error: {e}")
    
    # Try HuggingFace as fallback
    if huggingface_client:
        try:
            API_URL = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.1"
            headers = {"Authorization": f"Bearer {huggingface_client}"}
            payload = {"inputs": prompt, "parameters": {"max_new_tokens": 500}}
            response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if data and isinstance(data, list) and len(data) > 0:
                    return data[0].get('generated_text', '').replace(prompt, '').strip()
        except Exception as e:
            print(f"HuggingFace error: {e}")
    
    # Simple Bot as final fallback
    return generate_simple_response(prompt)

def generate_simple_response(prompt):
    """Simple rule-based responses when AI is unavailable"""
    prompt_lower = prompt.lower()    
    # 🔒 SECURITY FIX: Escape the prompt before echoing it back to prevent XSS
    safe_prompt = html.escape(prompt)
    
    greetings = ['hello', 'hi', 'hey', 'greetings', 'howdy']
    if any(word in prompt_lower for word in greetings):
        return "Hello! 👋 I'm BRICK AI. How can I help you today?"
    
    if 'how are you' in prompt_lower:
        return "I'm doing great! Thanks for asking. How can I assist you?"
    
    if 'help' in prompt_lower:
        return "I can help you with:\n• Answering questions\n• Providing information\n• Chatting about various topics\n• Search assistance\n\nWhat would you like to know?"
    
    if 'weather' in prompt_lower:
        return "I don't have access to real-time weather data, but you can check weather websites for accurate forecasts! 🌤️"
    
    if 'time' in prompt_lower or 'date' in prompt_lower:
        from datetime import datetime
        now = datetime.now()
        return f"The current time is {now.strftime('%I:%M %p')} on {now.strftime('%B %d, %Y')} 📅"
    
    if 'thank' in prompt_lower:
        return "You're welcome! 😊 Is there anything else I can help you with?"
    
    if 'bye' in prompt_lower or 'goodbye' in prompt_lower:
        return "Goodbye! 👋 Feel free to come back anytime. Have a great day!"
    
    # Default response
    return f"""🤖 BRICK AI here! 

I understand you're asking about: "{safe_prompt}"

Since I'm currently in simple mode, here's what I can tell you:
• Try searching for this using the Search tab
• I can chat with you about general topics
• Ask me anything else!

Is there something specific you'd like to know?"""

def smart_search(query):
    """AI-powered search with fallback"""
    prompt = f"""Provide a comprehensive answer to: {query}
    
    Format:
    1. Brief overview
    2. Key points
    3. Summary"""
    
    result = query_ai(prompt)    return result if result else "AI search is currently unavailable."

def chat_with_ai(message):
    """Chat with AI with fallback"""
    prompt = f"""You are BRICK AI, a friendly assistant. Respond to: {message}
    
    Be conversational and helpful. Keep responses natural and engaging."""
    
    result = query_ai(prompt)
    return result if result else "I'm having trouble responding. Could you try again?"

# Search Functions
def search_google(query):
    if not google_search:
        return []
    try:
        results = []
        search_results = google_search(query, num_results=5, stop=5, pause=1)
        for url in search_results:
            results.append(url)
        return results
    except Exception as e:
        print(f"Google search error: {e}")
        return []

def search_bing(query):
    try:
        bing_api_key = os.environ.get("BING_API_KEY", "")
        if bing_api_key:
            headers = {"Ocp-Apim-Subscription-Key": bing_api_key}
            params = {"q": query, "mkt": "en-us", "count": 3}
            response = requests.get("https://api.bing.microsoft.com/v7.0/search", headers=headers, params=params, timeout=10)
            data = response.json()
            return [r['url'] for r in data.get('webPages', {}).get('value', [])[:3]]
        return []
    except Exception as e:
        print(f"Bing search error: {e}")
        return []

def search_wikipedia(query):
    if not wikipedia:
        return []
    try:
        results = wikipedia.search(query, results=3)
        summaries = []
        for title in results:
            try:
                page = wikipedia.page(title)
                summary = wikipedia.summary(title, sentences=3)
                summaries.append({                    'title': title,
                    'summary': summary,
                    'url': page.url
                })
            except:
                continue
        return summaries
    except Exception as e:
        print(f"Wikipedia search error: {e}")
        return []

# Templates
MAIN_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BRICK AI 👾 - Search & Chat</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: {% if session.get('theme') == 'dark' %}linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 50%, #16213e 100%){% else %}linear-gradient(135deg, #667eea 0%, #764ba2 100%){% endif %};
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
        .header h1 { 
            font-size: 32px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        /* Glowing Green Title - FIXED */
        .glow-title {
            color: #00ff41 !important;
            text-shadow: 
                0 0 5px #00ff41,                0 0 10px #00ff41,
                0 0 20px #00ff41,
                0 0 40px #00ff41,
                0 0 80px #00ff41,
                0 0 120px #00ff41 !important;
            animation: glowPulse 2s ease-in-out infinite;
            font-weight: bold;
            font-size: 32px;
        }
        @keyframes glowPulse {
            0%, 100% {
                text-shadow: 
                    0 0 5px #00ff41,
                    0 0 10px #00ff41,
                    0 0 20px #00ff41,
                    0 0 40px #00ff41,
                    0 0 80px #00ff41;
            }
            50% {
                text-shadow: 
                    0 0 10px #00ff41,
                    0 0 20px #00ff41,
                    0 0 40px #00ff41,
                    0 0 80px #00ff41,
                    0 0 160px #00ff41,
                    0 0 200px #00ff41;
            }
        }
        .header h1 span { font-size: 36px; }
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
        .btn-icon:hover { background: #5a6fd6; transform: translateY(-2px); box-shadow: 0 4px 12px rgba(102,126,234,0.4); }
        .btn-danger { background: #e74c3c; }
        .btn-danger:hover { background: #c0392b; transform: translateY(-2px); box-shadow: 0 4px 12px rgba(231,76,60,0.4); }
        
        .tab-navigation {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;            flex-wrap: wrap;
        }
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
            min-width: 120px;
        }
        .tab-btn:hover { background: white; transform: translateY(-2px); }
        .tab-btn.active { background: #667eea; color: white; box-shadow: 0 4px 12px rgba(102,126,234,0.4); }
        
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
            transition: border-color 0.3s;
        }
        .search-input:focus { outline: none; border-color: #00ff41; box-shadow: 0 0 20px rgba(0,255,65,0.3); }
        
        .search-mode {
            display: flex;
            gap: 8px;
            margin-bottom: 15px;
            flex-wrap: nowrap;
            overflow-x: auto;
        }
        .mode-btn {
            padding: 8px 14px;
            border: 2px solid #667eea;
            background: white;            color: #667eea;
            border-radius: 8px;
            cursor: pointer;
            font-weight: bold;
            font-size: 13px;
            transition: all 0.3s;
            white-space: nowrap;
            flex: 1;
            min-width: 70px;
            text-align: center;
        }
        .mode-btn.active { background: #667eea; color: white; }
        .mode-btn:hover { background: #667eea; color: white; transform: translateY(-2px); }
        
        .search-btn {
            width: 100%;
            padding: 15px;
            background: linear-gradient(135deg, #00ff41, #00cc33);
            color: #0a0a0a;
            border: none;
            border-radius: 10px;
            font-size: 18px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
            box-shadow: 0 0 20px rgba(0,255,65,0.3);
        }
        .search-btn:hover { 
            transform: translateY(-2px); 
            box-shadow: 0 0 40px rgba(0,255,65,0.5);
        }
        .search-btn:disabled { opacity: 0.7; cursor: not-allowed; transform: none; }
        
        /* Loading Animation - BLINKING 👾 */
        .loading-container {
            display: none;
            text-align: center;
            padding: 40px;
            background: rgba(255,255,255,0.95);
            border-radius: 15px;
            margin: 20px 0;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
        .loading-container.active {
            display: block;
            animation: fadeIn 0.3s;
        }
        .blinking-emoji {
            font-size: 64px;
            display: inline-block;            animation: blink 0.8s infinite;
        }
        @keyframes blink {
            0%, 100% { opacity: 1; transform: scale(1) rotate(0deg); }
            25% { transform: scale(1.1) rotate(-5deg); }
            50% { opacity: 0.3; transform: scale(0.8) rotate(0deg); }
            75% { transform: scale(1.1) rotate(5deg); }
        }
        .loading-text {
            font-size: 22px;
            color: #00ff41;
            margin-top: 15px;
            font-weight: bold;
            text-shadow: 0 0 20px rgba(0,255,65,0.5);
        }
        .loading-subtext {
            color: #666;
            margin-top: 5px;
            font-size: 14px;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
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
        .chat-header-actions {
            display: flex;
            justify-content: flex-end;
            margin-bottom: 10px;
            gap: 10px;
        }
        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 10px;
            margin-bottom: 15px;
            background: #f8f9ff;
            border-radius: 10px;
            min-height: 400px;
            max-height: 450px;
        }        .chat-message {
            margin-bottom: 15px;
            padding: 12px 16px;
            border-radius: 12px;
            max-width: 80%;
            animation: fadeIn 0.3s;
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
            font-size: 11px;
            opacity: 0.7;
            margin-top: 5px;
            display: block;
        }
        .chat-message.user .time { color: rgba(255,255,255,0.8); }
        .chat-message.ai .time { color: #999; }
        .chat-input-area {
            display: flex;
            gap: 10px;
        }
        .chat-input {
            flex: 1;
            padding: 12px 16px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            font-size: 15px;
            transition: border-color 0.3s;
        }
        .chat-input:focus { outline: none; border-color: #00ff41; box-shadow: 0 0 20px rgba(0,255,65,0.3); }
        .chat-send-btn {
            padding: 12px 25px;
            background: linear-gradient(135deg, #00ff41, #00cc33);
            color: #0a0a0a;
            border: none;
            border-radius: 10px;
            font-size: 15px;
            font-weight: bold;
            cursor: pointer;            transition: all 0.3s;
            box-shadow: 0 0 20px rgba(0,255,65,0.3);
        }
        .chat-send-btn:hover { 
            transform: translateY(-2px); 
            box-shadow: 0 0 40px rgba(0,255,65,0.5);
        }
        .chat-send-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
        
        /* Chat Typing - BLINKING 👾 */
        .chat-typing {
            display: none;
            padding: 12px;
            color: #00ff41;
            font-style: italic;
            font-size: 16px;
            text-shadow: 0 0 20px rgba(0,255,65,0.3);
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
            border-left: 4px solid #00ff41;
            background: #f8f9ff;
            border-radius: 8px;
            animation: fadeIn 0.5s;
        }
        .source-header {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 15px;
            font-size: 20px;
            font-weight: bold;
            color: #00ff41;
            text-shadow: 0 0 10px rgba(0,255,65,0.3);
        }
        .source-icon { font-size: 24px; }        .result-item {
            margin-bottom: 15px;
            padding: 15px;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            animation: fadeIn 0.5s;
        }
        .result-title { font-weight: bold; color: #333; margin-bottom: 8px; font-size: 16px; }
        .result-summary { color: #666; line-height: 1.6; }
        .result-link {
            color: #00cc33;
            text-decoration: none;
            font-size: 14px;
            margin-top: 8px;
            display: inline-block;
        }
        .result-link:hover { text-decoration: underline; color: #00ff41; }
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
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
        .history-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }
        .history-section h2 {
            color: #00ff41;
            text-shadow: 0 0 10px rgba(0,255,65,0.3);
        }
        .history-item {
            padding: 12px;
            margin-bottom: 10px;
            background: #f8f9ff;
            border-radius: 8px;
            cursor: pointer;
            transition: background 0.3s;        }
        .history-item:hover { background: #e8eaff; }
        .history-item strong { color: #333; }
        .history-item small { color: #999; }
        
        @media (max-width: 600px) {
            .header { flex-direction: column; gap: 15px; }
            .search-mode { flex-wrap: nowrap; overflow-x: auto; padding-bottom: 5px; }
            .mode-btn { min-width: 60px; font-size: 11px; padding: 6px 10px; }
            .header-buttons { width: 100%; justify-content: center; }
            .tab-btn { min-width: 80px; font-size: 14px; padding: 10px 15px; }
            .chat-container { height: 500px; }
            .chat-message { max-width: 90%; }
            .glow-title { font-size: 24px; }
            .header h1 span { font-size: 28px; }
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
            <h1><span>👾</span> <span class="glow-title">BRICK AI</span></h1>
            <div class="header-buttons">
                <a href="/settings" class="btn-icon">⚙️ Settings</a>
                <button onclick="showFeedback()" class="btn-icon">💬 Feedback</button>
            </div>
        </div>
        
        <!-- Tab Navigation -->
        <div class="tab-navigation">
            <button class="tab-btn active" onclick="switchTab('search', this)">🔍 Search</button>
            <button class="tab-btn" onclick="switchTab('chat', this)">💬 Chat</button>
        </div>
        
        <!-- Search Tab -->
        <div id="searchTab" class="tab-content active">
            <div class="search-box">
                <input type="text" class="search-input" id="searchQuery" placeholder="What would you like to search?" value="{{ query if query else '' }}">
                <div class="search-mode">
                    <button class="mode-btn active" onclick="setMode('all', this)">🔍 All</button>                    <button class="mode-btn" onclick="setMode('google', this)">🌐 Google</button>
                    <button class="mode-btn" onclick="setMode('bing', this)">🔎 Bing</button>
                    <button class="mode-btn" onclick="setMode('wiki', this)">📚 Wiki</button>
                    <button class="mode-btn" onclick="setMode('ai', this)">🤖 AI</button>
                </div>
                <button class="search-btn" id="searchBtn" onclick="performSearch()">🚀 Search Now</button>
            </div>
            
            <!-- Loading Indicator with Blinking 👾 -->
            <div class="loading-container" id="searchLoading">
                <div class="blinking-emoji">👾</div>
                <div class="loading-text">BRICK AI is thinking...</div>
                <div class="loading-subtext">Searching across multiple sources</div>
            </div>
            
            {% if result %}
            <div class="results-container">
                {{ result|safe }}
            </div>
            {% endif %}
            
            {% if history %}
            <div class="history-section">
                <div class="history-header">
                    <h2>📜 Recent Searches</h2>
                    <!-- ✨ NEW FEATURE: Clear History Button -->
                    <button class="btn-icon btn-danger" onclick="clearHistory()">🗑️ Clear History</button>
                </div>
                {% for item in history %}
                <!-- 🔒 SECURITY FIX: Using data-attributes to prevent attribute injection -->
                <div class="history-item" data-query="{{ item.query|e }}" onclick="loadSearch(this.dataset.query)">
                    <strong>{{ item.query }}</strong>
                    <br><small>{{ item.timestamp }}</small>
                </div>
                {% endfor %}
            </div>
            {% endif %}
        </div>
        
        <!-- Chat Tab -->
        <div id="chatTab" class="tab-content">
            <div class="chat-container">
                <!-- ✨ NEW FEATURE: Export Chat Button -->
                <div class="chat-header-actions">
                    <a href="/export-chat" class="btn-icon" download>📥 Export Chat</a>
                </div>
                <div class="chat-messages" id="chatMessages">
                    <div class="chat-message ai">
                        <strong>👾 BRICK AI</strong>
                        <p>Hello! I'm BRICK AI, your friendly assistant. Ask me anything! 😊</p>                        <span class="time">Just now</span>
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
        
        // Tab switching
        function switchTab(tab, btn) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            
            if (tab === 'search') {
                document.getElementById('searchTab').classList.add('active');
            } else {
                document.getElementById('chatTab').classList.add('active');
            }
            btn.classList.add('active');
        }
        
        // Search functions
        function setMode(mode, btn) {
            currentMode = mode;
            document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        }
        
        function performSearch() {
            const query = document.getElementById('searchQuery').value;
            if (!query.trim()) { alert('Please enter a search query'); return; }
            
            // Show loading with blinking 👾
            const loading = document.getElementById('searchLoading');
            const results = document.querySelector('.results-container');
            const searchBtn = document.getElementById('searchBtn');
            
            loading.classList.add('active');
            searchBtn.disabled = true;
            searchBtn.textContent = '⏳ Searching...';
            if (results) results.style.display = 'none';            
            // Redirect with loading state
            setTimeout(() => {
                window.location.href = '/search?query=' + encodeURIComponent(query) + '&mode=' + currentMode + '&loading=true';
            }, 600);
        }
        
        function loadSearch(query) {
            document.getElementById('searchQuery').value = query;
            performSearch();
        }

        // ✨ NEW FEATURE: Clear History JS
        function clearHistory() {
            if(confirm('Are you sure you want to clear your search history?')) {
                fetch('/clear-history', { method: 'POST' })
                    .then(res => { if(res.ok) location.reload(); })
                    .catch(err => alert('Error clearing history'));
            }
        }
        
        // Chat functions
        function sendMessage() {
            const input = document.getElementById('chatInput');
            const message = input.value.trim();
            if (!message) return;
            
            // Add user message
            addMessage('user', message);
            input.value = '';
            input.disabled = true;
            document.getElementById('chatSendBtn').disabled = true;
            
            // Show typing indicator with blinking 👾
            document.getElementById('chatTyping').classList.add('active');
            
            const container = document.getElementById('chatMessages');
            container.scrollTop = container.scrollHeight;
            
            // Send to server
            fetch('/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message: message})
            })
            .then(response => response.json())
            .then(data => {
                document.getElementById('chatTyping').classList.remove('active');
                input.disabled = false;
                document.getElementById('chatSendBtn').disabled = false;                input.focus();
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
        
        // 🔒 SECURITY FIX: Using textContent instead of innerHTML to prevent XSS
        function addMessage(type, text) {
            const container = document.getElementById('chatMessages');
            const time = new Date().toLocaleTimeString();
            const div = document.createElement('div');
            div.className = 'chat-message ' + type;
            
            if (type === 'ai') {
                const strong = document.createElement('strong');
                strong.textContent = '👾 BRICK AI';
                div.appendChild(strong);
            }
            
            const p = document.createElement('p');
            p.textContent = text; // Safely handles text and prevents XSS
            div.appendChild(p);
            
            const timeSpan = document.createElement('span');
            timeSpan.className = 'time';
            timeSpan.textContent = time;
            div.appendChild(timeSpan);
            
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
                }).then(response => {                    if (response.ok) alert('Thank you for your feedback!');
                });
            }
        }
        
        // Enter key for search
        document.getElementById('searchQuery').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') performSearch();
        });
        
        // Check if loading from URL parameter
        window.onload = function() {
            const urlParams = new URLSearchParams(window.location.search);
            if (urlParams.get('loading') === 'true') {
                const loading = document.getElementById('searchLoading');
                loading.classList.add('active');
                const searchBtn = document.getElementById('searchBtn');
                searchBtn.disabled = true;
                searchBtn.textContent = '⏳ Searching...';
            }
        };
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
            background: {% if session.get('theme') == 'dark' %}linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 50%, #16213e 100%){% else %}linear-gradient(135deg, #667eea 0%, #764ba2 100%){% endif %};
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
        h1 { 
            text-align: center;             margin-bottom: 25px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
        }
        .glow-title {
            color: #00ff41 !important;
            text-shadow: 
                0 0 5px #00ff41,
                0 0 10px #00ff41,
                0 0 20px #00ff41,
                0 0 40px #00ff41 !important;
            animation: glowPulse 2s ease-in-out infinite;
        }
        @keyframes glowPulse {
            0%, 100% {
                text-shadow: 0 0 5px #00ff41, 0 0 10px #00ff41, 0 0 20px #00ff41, 0 0 40px #00ff41;
            }
            50% {
                text-shadow: 0 0 10px #00ff41, 0 0 20px #00ff41, 0 0 40px #00ff41, 0 0 80px #00ff41;
            }
        }
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
        .theme-btn.active { border-color: #00ff41; background: #f0fff4; box-shadow: 0 0 20px rgba(0,255,65,0.3); }
        .theme-btn:hover { border-color: #00ff41; transform: translateY(-2px); }
        .logout-btn {
            width: 100%;
            padding: 15px;
            background: #e74c3c;
            color: white;
            border: none;
            border-radius: 10px;            font-size: 16px;
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
            color: white;
            text-decoration: none;
            font-weight: bold;
        }
        .back-btn:hover { text-decoration: underline; color: #00ff41; }
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
            <h1>⚙️ <span class="glow-title">BRICK AI</span> Settings</h1>
            <div class="user-info">
                <strong>👤 Logged in as:</strong> {{ session.get('username') }}<br>                <strong>📧 Email:</strong> {{ session.get('user_email', 'N/A') }}
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
            padding: 20px;        }
        .login-box {
            background: rgba(255,255,255,0.95);
            padding: 40px;
            border-radius: 15px;
            width: 100%;
            max-width: 400px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
        h1 { 
            text-align: center; 
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
        }
        .glow-title {
            color: #00ff41 !important;
            text-shadow: 
                0 0 5px #00ff41,
                0 0 10px #00ff41,
                0 0 20px #00ff41,
                0 0 40px #00ff41 !important;
            animation: glowPulse 2s ease-in-out infinite;
        }
        @keyframes glowPulse {
            0%, 100% {
                text-shadow: 0 0 5px #00ff41, 0 0 10px #00ff41, 0 0 20px #00ff41, 0 0 40px #00ff41;
            }
            50% {
                text-shadow: 0 0 10px #00ff41, 0 0 20px #00ff41, 0 0 40px #00ff41, 0 0 80px #00ff41;
            }
        }
        .subtitle { text-align: center; color: #666; margin-bottom: 30px; }
        .input-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; color: #333; font-weight: 500; }
        input {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.3s;
        }
        input:focus { outline: none; border-color: #00ff41; box-shadow: 0 0 20px rgba(0,255,65,0.3); }
        .btn {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #00ff41, #00cc33);            color: #0a0a0a;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
            box-shadow: 0 0 20px rgba(0,255,65,0.3);
        }
        .btn:hover { transform: translateY(-2px); box-shadow: 0 0 40px rgba(0,255,65,0.5); }
        .flash {
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
            text-align: center;
        }
        .flash.error { background: #fee; color: #c00; border: 1px solid #fcc; }
        .flash.success { background: #efe; color: #080; border: 1px solid #cfc; }
        .links { text-align: center; margin-top: 20px; }
        .links a { color: #00cc33; text-decoration: none; font-weight: bold; }
        .links a:hover { text-decoration: underline; color: #00ff41; }
    </style>
</head>
<body>
    <div class="login-box">
        <h1>👾 <span class="glow-title">BRICK AI</span></h1>
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

REGISTER_TEMPLATE = '''<!DOCTYPE html>
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
            background: rgba(255,255,255,0.95);
            padding: 40px;
            border-radius: 15px;
            width: 100%;
            max-width: 400px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
        h1 { 
            text-align: center; 
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
        }
        .glow-title {
            color: #00ff41 !important;
            text-shadow: 
                0 0 5px #00ff41,
                0 0 10px #00ff41,
                0 0 20px #00ff41,
                0 0 40px #00ff41 !important;
            animation: glowPulse 2s ease-in-out infinite;
        }
        @keyframes glowPulse {
            0%, 100% {
                text-shadow: 0 0 5px #00ff41, 0 0 10px #00ff41, 0 0 20px #00ff41, 0 0 40px #00ff41;
            }
            50% {
                text-shadow: 0 0 10px #00ff41, 0 0 20px #00ff41, 0 0 40px #00ff41, 0 0 80px #00ff41;
            }
        }        .subtitle { text-align: center; color: #666; margin-bottom: 30px; }
        .input-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; color: #333; font-weight: 500; }
        input {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.3s;
        }
        input:focus { outline: none; border-color: #00ff41; box-shadow: 0 0 20px rgba(0,255,65,0.3); }
        .btn {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #00ff41, #00cc33);
            color: #0a0a0a;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
            box-shadow: 0 0 20px rgba(0,255,65,0.3);
        }
        .btn:hover { transform: translateY(-2px); box-shadow: 0 0 40px rgba(0,255,65,0.5); }
        .flash {
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
            text-align: center;
        }
        .flash.error { background: #fee; color: #c00; border: 1px solid #fcc; }
        .flash.success { background: #efe; color: #080; border: 1px solid #cfc; }
        .links { text-align: center; margin-top: 20px; }
        .links a { color: #00cc33; text-decoration: none; font-weight: bold; }
        .links a:hover { text-decoration: underline; color: #00ff41; }
    </style>
</head>
<body>
    <div class="register-box">
        <h1>👾 <span class="glow-title">BRICK AI</span></h1>
        <p class="subtitle">Create Your Account</p>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% for category, message in messages %}
                <div class="flash {{ category }}">{{ message }}</div>
            {% endfor %}
        {% endwith %}
        <form method="POST">
            <div class="input-group">                <label>Username</label>
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
        user = c.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
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
        
        existing = c.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        if existing:
            conn.close()
            flash('Email already registered!', 'error')
            return render_template_string(REGISTER_TEMPLATE)
        
        existing = c.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if existing:
            conn.close()
            flash('Username already taken!', 'error')
            return render_template_string(REGISTER_TEMPLATE)
        
        hashed_password = generate_password_hash(password)
        c.execute('INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
                 (username, email, hashed_password))
        conn.commit()
        user_id = c.lastrowid
        conn.close()
        
        session['user_id'] = user_id
        session['username'] = username
        session['user_email'] = email
        session['theme'] = 'light'
        
        flash('Account created successfully!', 'success')
        return redirect('/dashboard')
    
    return render_template_string(REGISTER_TEMPLATE)

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Please login first.', 'error')
        return redirect('/login')
        conn = get_db()
    c = conn.cursor()
    user = c.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    
    if not user:
        conn.close()
        session.clear()
        return redirect('/login')
    
    history = c.execute('SELECT * FROM search_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10',
                       (session['user_id'],)).fetchall()
    conn.close()
    
    return render_template_string(MAIN_TEMPLATE, result='', query='', history=history)

@app.route('/search', methods=['GET'])
def search():
    if 'user_id' not in session:
        flash('Please login first.', 'error')
        return redirect('/login')
    
    query = request.args.get('query', '')
    mode = request.args.get('mode', 'all')
    loading = request.args.get('loading', 'false')
    
    if not query:
        flash('Please enter a search query.', 'error')
        return redirect('/dashboard')
    
    # 🔒 SECURITY FIX: Escape the query immediately
    safe_query = html.escape(query)
    html_parts = []
    
    # Helper to validate URLs
    def safe_url(url):
        if url.startswith(('http://', 'https://')):
            return html.escape(url)
        return '#'
    
    # Google Search
    if mode in ['all', 'google']:
        try:
            google_results = search_google(query)
            if google_results:
                html_parts.append('<div class="source-section">')
                html_parts.append('<div class="source-header"><span class="source-icon">🌐</span> Google Search</div>')
                for i, url in enumerate(google_results[:5], 1):
                    s_url = safe_url(url)
                    html_parts.append(f'''
                    <div class="result-item">                        <div class="result-title">Result {i}</div>
                        <div class="result-summary">Click the link below to visit the page</div>
                        <a href="{s_url}" target="_blank" class="result-link">🔗 {s_url[:80]}...</a>
                    </div>
                    ''')
                html_parts.append('</div>')
        except Exception as e:
            pass
    
    # Bing Search
    if mode in ['all', 'bing']:
        try:
            bing_results = search_bing(query)
            if bing_results:
                html_parts.append('<div class="source-section">')
                html_parts.append('<div class="source-header"><span class="source-icon">🔎</span> Bing Search</div>')
                for i, url in enumerate(bing_results[:3], 1):
                    s_url = safe_url(url)
                    html_parts.append(f'''
                    <div class="result-item">
                        <div class="result-title">Result {i}</div>
                        <div class="result-summary">Click the link below to visit the page</div>
                        <a href="{s_url}" target="_blank" class="result-link">🔗 {s_url[:80]}...</a>
                    </div>
                    ''')
                html_parts.append('</div>')
        except Exception as e:
            pass
    
    # Wikipedia Search
    if mode in ['all', 'wiki']:
        try:
            wiki_results = search_wikipedia(query)
            if wiki_results:
                html_parts.append('<div class="source-section">')
                html_parts.append('<div class="source-header"><span class="source-icon">📚</span> Wikipedia</div>')
                for item in wiki_results:
                    s_title = html.escape(item['title'])
                    s_summary = html.escape(item['summary'])
                    s_url = safe_url(item['url'])
                    html_parts.append(f'''
                    <div class="result-item">
                        <div class="result-title">{s_title}</div>
                        <div class="result-summary">{s_summary}</div>
                        <a href="{s_url}" target="_blank" class="result-link">📖 Read More on Wikipedia</a>
                    </div>
                    ''')
                html_parts.append('</div>')
        except Exception as e:
            pass    
    # AI Search - Now with fallback
    if mode in ['all', 'ai']:
        try:
            ai_result = smart_search(query)
            if ai_result:
                # 🔒 SECURITY FIX: Escape AI result and convert newlines to <br>
                safe_ai_result = html.escape(ai_result).replace('\n', '<br>')
                html_parts.append('<div class="source-section">')
                html_parts.append('<div class="source-header"><span class="source-icon">🤖</span> AI Smart Summary</div>')
                html_parts.append(f'<div class="result-item"><div class="result-summary">{safe_ai_result}</div></div>')
                html_parts.append('</div>')
        except Exception as e:
            pass
    
    result_html = ''.join(html_parts) if html_parts else f'<p>No results found for "{safe_query}". Try a different search term.</p>'
    
    # Save to history
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT INTO search_history (user_id, query, result, mode) VALUES (?, ?, ?, ?)',
             (session['user_id'], query, result_html[:500], mode))
    conn.commit()
    conn.close()
    
    conn = get_db()
    c = conn.cursor()
    history = c.execute('SELECT * FROM search_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10',
                       (session['user_id'],)).fetchall()
    conn.close()
    
    return render_template_string(MAIN_TEMPLATE, result=result_html, query=query, history=history, loading=loading)

@app.route('/chat', methods=['POST'])
def chat():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    data = request.get_json()
    message = data.get('message', '')
    
    if not message:
        return jsonify({'error': 'No message provided'}), 400
    
    response = chat_with_ai(message)
    
    # Save chat to database
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT INTO chat_messages (user_id, message, response) VALUES (?, ?, ?)',             (session['user_id'], message, response))
    conn.commit()
    conn.close()
    
    return jsonify({'response': response})

# ✨ NEW FEATURE: Export Chat History
@app.route('/export-chat')
def export_chat():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    conn = get_db()
    c = conn.cursor()
    messages = c.execute('SELECT message, response, timestamp FROM chat_messages WHERE user_id = ? ORDER BY timestamp ASC',
                         (session['user_id'],)).fetchall()
    conn.close()
    
    output = [f"--- BRICK AI Chat History Export ---"]
    output.append(f"User: {session.get('username')}")
    output.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    for msg in messages:
        output.append(f"[{msg['timestamp']}] You: {msg['message']}")
        output.append(f"[{msg['timestamp']}] BRICK AI: {msg['response']}")
        output.append("-" * 40)
    
    return Response(
        "\n".join(output),
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment;filename=brick_ai_chat_history.txt"}
    )

# ✨ NEW FEATURE: Clear Search History
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

@app.route('/settings')
def settings():
    if 'user_id' not in session:        flash('Please login first.', 'error')
        return redirect('/login')
    
    conn = get_db()
    c = conn.cursor()
    user = c.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    search_count = c.execute('SELECT COUNT(*) FROM search_history WHERE user_id = ?', (session['user_id'],)).fetchone()[0]
    conn.close()
    
    if not user:
        session.clear()
        return redirect('/login')
    
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