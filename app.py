from flask import Flask, render_template_string, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
import requests
import wikipedia
import traceback
import html
from datetime import datetime
from googlesearch import search as google_search

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'brick_ai_super_secret_key_123')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///brick_ai.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Get API keys from environment variables
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
HUGGINGFACE_API_KEY = os.environ.get("HUGGINGFACE_API_KEY", "")

# Login decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    auth_provider = db.Column(db.String(50), default='local')
    theme = db.Column(db.String(50), default='light')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    searches = db.relationship('SearchHistory', backref='user', lazy=True)
    feedback = db.relationship('Feedback', backref='user', lazy=True)

class SearchHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    query = db.Column(db.String(500), nullable=False)
    result = db.Column(db.Text)
    mode = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    rating = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# Initialize Gemini AI
gemini_client = None
USE_OLD_GEMINI = False

def init_gemini():
    global gemini_client, USE_OLD_GEMINI
    if not GEMINI_API_KEY or GEMINI_API_KEY == "":
        print("⚠️ No Gemini API key found - using Simple Bot only")
        return
    
    try:
        from google import genai
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        USE_OLD_GEMINI = False
        print("✅ Gemini AI initialized with new client")
    except ImportError:
        try:
            import google.generativeai as genai_old
            genai_old.configure(api_key=GEMINI_API_KEY)
            gemini_client = genai_old.GenerativeModel('gemini-1.5-flash')
            USE_OLD_GEMINI = True
            print("✅ Gemini AI initialized with old client")
        except ImportError:
            print("⚠️ Gemini library not installed")
    except Exception as e:
        print(f"⚠️ Error initializing Gemini: {e}")

def query_gemini(prompt):
    global gemini_client, USE_OLD_GEMINI
    if not gemini_client:
        return None
    
    try:
        if USE_OLD_GEMINI:
            response = gemini_client.generate_content(prompt)
            return response.text
        else:
            response = gemini_client.models.generate_content(
                model='gemini-1.5-flash',
                contents=prompt
            )
            return response.text
    except Exception as e:
        print(f"❌ Gemini error: {e}")
        return None

# Multi-Source Search Functions
def search_google(query):
    """Search Google and return top results"""
    try:
        results = []
        for url in google_search(query, num_results=3):
            results.append(url)
        return results
    except Exception as e:
        print(f"Google search error: {e}")
        return []

def search_bing(query):
    """Search Bing using API or web scraping"""
    try:
        # Using Bing Search API if available
        bing_api_key = os.environ.get("BING_API_KEY", "")
        if bing_api_key:
            headers = {"Ocp-Apim-Subscription-Key": bing_api_key}
            params = {"q": query, "mkt": "en-us"}
            endpoint = "https://api.bing.microsoft.com/v7.0/search"
            response = requests.get(endpoint, headers=headers, params=params)
            data = response.json()
            return [result['url'] for result in data.get('webPages', {}).get('value', [])[:3]]
        else:
            # Fallback: return message
            return ["Bing API key not configured"]
    except Exception as e:
        print(f"Bing search error: {e}")
        return []

def search_wikipedia(query):
    """Search Wikipedia and return summary"""
    try:
        results = wikipedia.search(query, results=3)
        summaries = []
        for title in results:
            try:
                page = wikipedia.page(title)
                summary = wikipedia.summary(title, sentences=3)
                summaries.append({
                    'title': title,
                    'summary': summary,
                    'url': page.url
                })
            except:
                continue
        return summaries
    except Exception as e:
        print(f"Wikipedia search error: {e}")
        return []

def smart_search(query):
    """Use AI to provide intelligent search results"""
    prompt = f"""Provide a comprehensive answer to this query: {query}
    
    Include:
    - Key facts
    - Important details
    - Related information
    
    Keep it concise but informative."""
    
    result = query_gemini(prompt)
    return result if result else "Smart search unavailable"

def summarize_content(url):
    """Extract and summarize content from a URL"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        
        # Simple extraction (in production, use BeautifulSoup)
        text = response.text[:2000]  # First 2000 chars
        
        # Ask AI to summarize
        prompt = f"Summarize this content in 2-3 sentences:\n\n{text[:500]}"
        summary = query_gemini(prompt)
        
        return summary if summary else text[:300] + "..."
    except Exception as e:
        print(f"Summarization error: {e}")
        return "Unable to fetch content"

# Templates
MAIN_APP_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BRICK AI - Multi-Source Search</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: {% if session.get('theme') == 'dark' %}linear-gradient(135deg, #1e3c72 0%, #2a5298 100%){% else %}linear-gradient(135deg, #667eea 0%, #764ba2 100%){% endif %};
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 900px;
            margin: 0 auto;
        }        
        .header {
            background: rgba(255, 255, 255, 0.95);
            padding: 20px;
            border-radius: 15px;
            margin-bottom: 20px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .header h1 {
            color: #667eea;
            font-size: 28px;
        }
        
        .header-buttons {
            display: flex;
            gap: 10px;
        }
        
        .btn-icon {
            background: #667eea;
            color: white;
            border: none;
            padding: 10px 15px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 16px;
            text-decoration: none;
        }
        
        .search-box {
            background: rgba(255, 255, 255, 0.95);
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
        .search-input:focus {
            outline: none;
            border-color: #667eea;
        }
        
        .search-mode {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-bottom: 15px;
        }
        
        .mode-btn {
            padding: 10px 20px;
            border: 2px solid #667eea;
            background: white;
            color: #667eea;
            border-radius: 8px;
            cursor: pointer;
            font-weight: bold;
        }
        
        .mode-btn.active {
            background: #667eea;
            color: white;
        }
        
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
        }
        
        .results-container {
            background: rgba(255, 255, 255, 0.95);
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
        
        .source-icon {
            font-size: 24px;
        }
        
        .result-item {
            margin-bottom: 15px;
            padding: 15px;
            background: white;
            border-radius: 8px;
        }
        
        .result-title {
            font-weight: bold;
            color: #333;
            margin-bottom: 8px;
        }
        
        .result-summary {
            color: #666;
            line-height: 1.6;
        }
        
        .result-link {
            color: #667eea;
            text-decoration: none;
            font-size: 14px;
            margin-top: 8px;
            display: inline-block;
        }
        
        .loading {
            text-align: center;
            padding: 40px;
            color: #667eea;
            font-size: 18px;
        }        
        .history-section {
            margin-top: 20px;
            padding: 20px;
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
        }
        
        .history-item {
            padding: 12px;
            margin-bottom: 10px;
            background: #f8f9ff;
            border-radius: 8px;
            cursor: pointer;
        }
        
        .history-item:hover {
            background: #e8eaff;
        }
        
        .flash-messages {
            margin-bottom: 20px;
        }
        
        .flash {
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 10px;
        }
        
        .flash.error {
            background: #fee;
            color: #c00;
            border: 1px solid #fcc;
        }
        
        .flash.success {
            background: #efe;
            color: #080;
            border: 1px solid #cfc;
        }
        
        @media (max-width: 600px) {
            .header {
                flex-direction: column;
                gap: 15px;
            }
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
                <a href="{{ url_for('settings') }}" class="btn-icon">⚙️ Settings</a>
                <button onclick="showFeedback()" class="btn-icon">💬 Feedback</button>
            </div>
        </div>
        
        <div class="search-box">
            <input type="text" class="search-input" id="searchQuery" placeholder="What would you like to search?" value="{{ query if query else '' }}">
            
            <div class="search-mode">
                <button class="mode-btn active" onclick="setMode('all')">🔍 All Sources</button>
                <button class="mode-btn" onclick="setMode('google')">🌐 Google</button>
                <button class="mode-btn" onclick="setMode('bing')">🔎 Bing</button>
                <button class="mode-btn" onclick="setMode('wiki')">📚 Wikipedia</button>
                <button class="mode-btn" onclick="setMode('ai')">🤖 AI Smart Search</button>
            </div>
            
            <button class="search-btn" onclick="performSearch()">🚀 Search Now</button>
        </div>
        
        {% if result %}
        <div class="results-container">
            {{ result|safe }}
        </div>
        {% endif %}
        
        {% if history %}
        <div class="history-section">
            <h2 style="margin-bottom: 15px; color: #667eea;">📜 Recent Searches</h2>
            {% for item in history %}
            <div class="history-item" onclick="loadSearch('{{ item.query }}')">
                <strong>{{ item.query }}</strong>
                <br><small style="color: #666;">{{ item.timestamp.strftime('%Y-%m-%d %H:%M') }}</small>
            </div>
            {% endfor %}
        </div>
        {% endif %}
    </div>
    
    <script>
        let currentMode = 'all';
        
        function setMode(mode) {
            currentMode = mode;
            document.querySelectorAll('.mode-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            event.target.classList.add('active');
        }
        
        function performSearch() {
            const query = document.getElementById('searchQuery').value;
            if (!query.trim()) {
                alert('Please enter a search query');
                return;
            }
            
            window.location.href = '/search?query=' + encodeURIComponent(query) + '&mode=' + currentMode;
        }
        
        function loadSearch(query) {
            document.getElementById('searchQuery').value = query;
            performSearch();
        }
        
        function showFeedback() {
            const feedback = prompt('We value your feedback! Please share your thoughts:');
            if (feedback) {
                fetch('/submit-feedback', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: feedback})
                }).then(response => {
                    if (response.ok) {
                        alert('Thank you for your feedback!');
                    }
                });
            }
        }
        
        // Allow Enter key to search
        document.getElementById('searchQuery').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                performSearch();
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
    <title>Settings - BRICK AI</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: {% if session.get('theme') == 'dark' %}linear-gradient(135deg, #1e3c72 0%, #2a5298 100%){% else %}linear-gradient(135deg, #667eea 0%, #764ba2 100%){% endif %};
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 600px;
            margin: 0 auto;
        }
        
        .settings-card {
            background: rgba(255, 255, 255, 0.95);
            padding: 30px;
            border-radius: 15px;
            margin-bottom: 20px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
        
        h1 {
            color: #667eea;
            margin-bottom: 25px;
            text-align: center;
        }
        
        .setting-item {
            margin-bottom: 25px;
            padding-bottom: 20px;
            border-bottom: 1px solid #e0e0e0;
        }
        
        .setting-item:last-child {
            border-bottom: none;
        }
        
        .setting-label {
            font-weight: bold;
            color: #333;
            margin-bottom: 10px;
            display: block;
        }
        
        .theme-options {
            display: flex;
            gap: 15px;
        }
        
        .theme-btn {
            flex: 1;
            padding: 15px;
            border: 2px solid #e0e0e0;
            background: white;
            border-radius: 10px;
            cursor: pointer;
            font-size: 16px;
        }
        
        .theme-btn.active {
            border-color: #667eea;
            background: #f8f9ff;
        }
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
        
        .back-btn {
            display: inline-block;
            margin-bottom: 20px;
            color: #667eea;
            text-decoration: none;
            font-weight: bold;
        }
        
        .user-info {
            background: #f8f9ff;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        
        .flash-messages {
            margin-bottom: 20px;
        }
        
        .flash {
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 10px;
        }
        
        .flash.error {
            background: #fee;
            color: #c00;
            border: 1px solid #fcc;
        }
        
        .flash.success {
            background: #efe;
            color: #080;
            border: 1px solid #cfc;
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
        
        <a href="{{ url_for('home') }}" class="back-btn">← Back to Home</a>
        
        <div class="settings-card">
            <h1>⚙️ App Settings</h1>
            
            <div class="user-info">
                <strong>👤 Logged in as:</strong> {{ session.get('username') }}<br>
                <strong>📧 Email:</strong> {{ session.get('user_email', 'N/A') }}
            </div>
            
            <div class="setting-item">
                <span class="setting-label">🎨 App Theme</span>
                <div class="theme-options">
                    <button class="theme-btn {% if session.get('theme') != 'dark' %}active{% endif %}" onclick="setTheme('light')">
                        ☀️ Light
                    </button>
                    <button class="theme-btn {% if session.get('theme') == 'dark' %}active{% endif %}" onclick="setTheme('dark')">
                        🌙 Dark
                    </button>
                </div>
            </div>
            
            <div class="setting-item">
                <span class="setting-label">📊 Account Stats</span>
                <p>Total Searches: {{ search_count }}</p>
                <p>Member Since: {{ user.created_at.strftime('%B %Y') if user else 'N/A' }}</p>
            </div>
            
            <div class="setting-item">
                <span class="setting-label">🔐 Account</span>
                <a href="{{ url_for('logout') }}" class="logout-btn">🚪 Logout</a>
            </div>
        </div>
    </div>
    
    <script>
        function setTheme(theme) {
            fetch('/set-theme', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({theme: theme})
            }).then(() => {
                location.reload();
            });
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
    <title>Login - BRICK AI</title>
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
            background: rgba(255, 255, 255, 0.95);
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            width: 100%;
            max-width: 400px;
        }
        h1 { color: #667eea; text-align: center; margin-bottom: 10px; }
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
            margin-bottom: 15px;
        }
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
        
        <div class="links">
            <a href="{{ url_for('register') }}">Create an Account</a>
        </div>
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
    <title>Register - BRICK AI</title>
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
            background: rgba(255, 255, 255, 0.95);
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            width: 100%;
            max-width: 400px;
        }
        h1 { color: #667eea; text-align: center; margin-bottom: 10px; }
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
            margin-bottom: 15px;
        }
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
    </style>
</head>
<body>
    <div class="register-box">
        <h1>👾 Create Account</h1>
        <p class="subtitle">Join BRICK AI Today</p>
        
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
        
        <div class="links">
            <a href="{{ url_for('login') }}">Already have an account? Login</a>
        </div>
    </div>
</body>
</html>
'''

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('home'))
    return redirect(url_for('login'))

@app.route("/login", methods=['GET', 'POST'])
def login():
    # If already logged in, go to home
    if 'user_id' in session:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email, auth_provider='local').first()
        
        if user and check_password_hash(user.password_hash, password):
            # Set ALL session variables
            session['user_id'] = user.id
            session['username'] = user.username
            session['user_email'] = user.email
            session['theme'] = user.theme if user.theme else 'light'
            session['auth_provider'] = user.auth_provider
            
            flash('Logged in successfully!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid email or password!', 'error')
    
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered!', 'error')
            return render_template_string(REGISTER_TEMPLATE)
        
        if User.query.filter_by(username=username).first():
            flash('Username already taken!', 'error')
            return render_template_string(REGISTER_TEMPLATE)
        
        hashed_password = generate_password_hash(password)
        new_user = User(username=username, email=email, password_hash=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        
        # Auto-login after registration
        session['user_id'] = new_user.id
        session['username'] = new_user.username
        session['user_email'] = new_user.email
        session['theme'] = new_user.theme
        session['auth_provider'] = new_user.auth_provider
        
        flash('Account created and logged in successfully!', 'success')
        return redirect(url_for('home'))
    
    return render_template_string(REGISTER_TEMPLATE)

@app.route("/logout")
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

@app.route("/settings")
@login_required
def settings():
    user = User.query.get(session['user_id'])
    search_count = SearchHistory.query.filter_by(user_id=user.id).count()
    
    return render_template_string(SETTINGS_TEMPLATE, user=user, search_count=search_count)

@app.route('/set-theme', methods=['POST'])
@login_required
def set_theme():
    data = request.get_json()
    theme = data.get('theme', 'light')
    
    user = User.query.get(session['user_id'])
    user.theme = theme
    session['theme'] = theme
    db.session.commit()
    
    return jsonify({'success': True})

@app.route("/submit-feedback", methods=['POST'])
@login_required
def submit_feedback():
    data = request.get_json()
    message = data.get('message', '')
    
    if message:
        feedback = Feedback(user_id=session['user_id'], message=message)
        db.session.add(feedback)
        db.session.commit()
    
    return jsonify({'success': True})

@app.route("/", methods=["GET", "POST"])
@login_required
def home():
    result = ""
    query = ""
    gemini_available = gemini_client is not None
    huggingface_available = bool(HUGGINGFACE_API_KEY)
    
    history = SearchHistory.query.filter_by(user_id=session['user_id']).order_by(
        SearchHistory.timestamp.desc()
    ).limit(10).all()
    
    return render_template_string(
        MAIN_APP_TEMPLATE,
        result=result,
        query=query,
        history=history,
        gemini_available=gemini_available,
        huggingface_available=huggingface_available
    )

@app.route("/search", methods=["GET"])
@login_required
def search():
    query = request.args.get('query', '')
    mode = request.args.get('mode', 'all')
    
    if not query:
        flash('Please enter a search query.', 'error')
        return redirect(url_for('home'))
    
    result_html = perform_multi_search(query, mode)
    
    # Save to history
    new_search = SearchHistory(
        user_id=session['user_id'],
        query=query,
        result=result_html[:1000] if result_html else "",
        mode=mode
    )
    db.session.add(new_search)
    db.session.commit()
    
    history = SearchHistory.query.filter_by(user_id=session['user_id']).order_by(
        SearchHistory.timestamp.desc()
    ).limit(10).all()
    
    return render_template_string(
        MAIN_APP_TEMPLATE,
        result=result_html,
        query=query,
        history=history,
        gemini_available=True,
        huggingface_available=True
    )

def perform_multi_search(query, mode='all'):
    html_parts = []
    
    if mode in ['all', 'google']:
        html_parts.append('<h2 style="color: #667eea; margin-bottom: 15px;">🔍 Multi-Source Search Results</h2>')
    
    # Google Search
    if mode in ['all', 'google']:
        google_results = search_google(query)
        if google_results:
            html_parts.append('<div class="source-section">')
            html_parts.append('<div class="source-header"><span class="source-icon">🌐</span> Google Search</div>')
            for i, url in enumerate(google_results[:3], 1):
                summary = summarize_content(url)
                html_parts.append(f'''
                <div class="result-item">
                    <div class="result-title">Result {i}</div>
                    <div class="result-summary">{summary}</div>
                    <a href="{url}" target="_blank" class="result-link">→ View on Google</a>
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
                if url != "Bing API key not configured":
                    summary = summarize_content(url)
                    html_parts.append(f'''
                    <div class="result-item">
                        <div class="result-title">Result {i}</div>
                        <div class="result-summary">{summary}</div>
                        <a href="{url}" target="_blank" class="result-link">→ View on Bing</a>
                    </div>
                    ''')
            html_parts.append('</div>')
    
    # Wikipedia
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
                    <a href="{item['url']}" target="_blank" class="result-link">→ Read More on Wikipedia</a>
                </div>
                ''')
            html_parts.append('</div>')
    
    # AI Smart Search
    if mode in ['all', 'ai']:
        smart_result = smart_search(query)
        if smart_result:
            html_parts.append('<div class="source-section">')
            html_parts.append('<div class="source-header"><span class="source-icon">🤖</span> AI Smart Summary</div>')
            html_parts.append(f'<div class="result-item"><div class="result-summary">{smart_result}</div></div>')
            html_parts.append('</div>')
    
    return ''.join(html_parts) if html_parts else '<p>No results found. Try a different search.</p>'

# Initialize database
with app.app_context():
    db.create_all()
    init_gemini()
    print("✅ Database ready!")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)