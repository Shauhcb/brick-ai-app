import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template_string, request, redirect, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import requests
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'brick_ai_super_secret_key_123')

# Database connection function for Supabase PostgreSQL
def get_db():
    try:
        conn = psycopg2.connect(
            os.environ.get('DATABASE_URL'),
            cursor_factory=RealDictCursor
        )
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

def init_db():
    conn = get_db()
    if not conn:
        print("❌ Could not connect to database")
        return
    
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        theme TEXT DEFAULT 'light',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Search history table
    c.execute('''CREATE TABLE IF NOT EXISTS search_history (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        query TEXT NOT NULL,
        result TEXT,
        mode TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Feedback table
    c.execute('''CREATE TABLE IF NOT EXISTS feedback (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        message TEXT NOT NULL,
        rating INTEGER,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Chat messages table
    c.execute('''CREATE TABLE IF NOT EXISTS chat_messages (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        message TEXT NOT NULL,
        response TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized on Supabase!")

# Initialize database
init_db()

# Try importing optional packages
try:
    import wikipedia
    print("✅ Wikipedia loaded")
except ImportError:
    wikipedia = None

try:
    from googlesearch import search as google_search
    print("✅ Google search loaded")
except ImportError:
    google_search = None

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
    return """I'm BRICK AI! 😊

I'm currently in offline mode, but I can still help!

Try asking me:
• Questions about anything
• For search assistance
• General conversation

What would you like to know?"""

# Search Functions
def search_google(query):
    if not google_search:
        return []
    try:
        results = []
        for url in google_search(query, num_results=5, stop=5, pause=1):
            results.append(url)
        return results
    except:
        return []

def search_bing(query):
    try:
        bing_key = os.environ.get("BING_API_KEY", "")
        if bing_key:
            headers = {"Ocp-Apim-Subscription-Key": bing_key}
            params = {"q": query, "count": 3}
            response = requests.get("https://api.bing.microsoft.com/v7.0/search", headers=headers, params=params, timeout=5)
            data = response.json()
            return [r['url'] for r in data.get('webPages', {}).get('value', [])[:3]]
        return []
    except:
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
                summaries.append({
                    'title': title,
                    'summary': wikipedia.summary(title, sentences=2),
                    'url': page.url
                })
            except:
                continue
        return summaries
    except:
        return []

# Templates (I'll keep them short since they're in the Python file)
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
        h1 { 
            text-align: center; 
            margin-bottom: 10px;
            font-size: 32px;
            color: #667eea;
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
        <form method="POST" action="/login">
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
        h1 { 
            text-align: center; 
            margin-bottom: 10px;
            font-size: 32px;
            color: #667eea;
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
        <form method="POST" action="/register">
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
    <title>BRICK AI 👾 - Search & Chat</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
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
            color: #667eea;
        }
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
        
        .tab-navigation {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
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
        .chat-message.user {
            background: #667eea;
            color: white;
            margin-left: auto;
        }
        .chat-message.ai {
            background: white;
            color: #333;
            margin-right: auto;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }
        .chat-message .time {
            font-size: 11px;
            opacity: 0.7;
            margin-top: 5px;
            display: block;
        }
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
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 600px; margin: 0 auto; }
        .settings-card {
            background: white;
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
        h1 { 
            text-align: center; 
            margin-bottom: 25px;
            color: #667eea;
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
                    <button class="theme-btn active" onclick="setTheme('light')">☀️ Light</button>
                    <button class="theme-btn" onclick="setTheme('dark')">🌙 Dark</button>
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
        if not conn:
            flash('Database connection error!', 'error')
            return render_template_string(LOGIN_TEMPLATE)
        
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE email = %s', (email,))
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
        if not conn:
            flash('Database connection error!', 'error')
            return render_template_string(REGISTER_TEMPLATE)
        
        c = conn.cursor()
        
        c.execute('SELECT * FROM users WHERE email = %s', (email,))
        if c.fetchone():
            conn.close()
            flash('Email already registered!', 'error')
            return render_template_string(REGISTER_TEMPLATE)
        
        c.execute('SELECT * FROM users WHERE username = %s', (username,))
        if c.fetchone():
            conn.close()
            flash('Username already taken!', 'error')
            return render_template_string(REGISTER_TEMPLATE)
        
        hashed_password = generate_password_hash(password)
        c.execute('INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)',
                 (username, email, hashed_password))
        conn.commit()
        
        c.execute('SELECT * FROM users WHERE email = %s', (email,))
        user = c.fetchone()
        conn.close()
        
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['user_email'] = user['email']
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
    if not conn:
        flash('Database connection error!', 'error')
        return redirect('/login')
    
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE id = %s', (session['user_id'],))
    user = c.fetchone()
    
    if not user:
        conn.close()
        session.clear()
        return redirect('/login')
    
    c.execute('SELECT * FROM search_history WHERE user_id = %s ORDER BY timestamp DESC LIMIT 10', (session['user_id'],))
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
    
    # AI Search
    if mode in ['all', 'ai']:
        ai_result = get_ai_response(f"Provide a comprehensive answer to: {query}")
        if ai_result:
            html_parts.append('<div class="source-section">')
            html_parts.append('<div class="source-header"><span class="source-icon">🤖</span> AI Smart Summary</div>')
            html_parts.append(f'<div class="result-item"><div class="result-summary">{ai_result}</div></div>')
            html_parts.append('</div>')
    
    result_html = ''.join(html_parts) if html_parts else f'<p style="color:#666;text-align:center;padding:20px;">No results found for "{query}". Try a different search term.</p>'
    
    # Save to history
    conn = get_db()
    if conn:
        c = conn.cursor()
        c.execute('INSERT INTO search_history (user_id, query, result, mode) VALUES (%s, %s, %s, %s)',
                 (session['user_id'], query, result_html[:500], mode))
        conn.commit()
        conn.close()
    
    conn = get_db()
    if conn:
        c = conn.cursor()
        c.execute('SELECT * FROM search_history WHERE user_id = %s ORDER BY timestamp DESC LIMIT 10', (session['user_id'],))
        history = c.fetchall()
        conn.close()
    else:
        history = []
    
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
    if conn:
        c = conn.cursor()
        c.execute('INSERT INTO chat_messages (user_id, message, response) VALUES (%s, %s, %s)',
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
    if not conn:
        flash('Database connection error!', 'error')
        return redirect('/login')
    
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE id = %s', (session['user_id'],))
    user = c.fetchone()
    c.execute('SELECT COUNT(*) FROM search_history WHERE user_id = %s', (session['user_id'],))
    search_count = c.fetchone()[0]
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
    if conn:
        c = conn.cursor()
        c.execute('UPDATE users SET theme = %s WHERE id = %s', (theme, session['user_id']))
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
        if conn:
            c = conn.cursor()
            c.execute('INSERT INTO feedback (user_id, message) VALUES (%s, %s)', (session['user_id'], message))
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