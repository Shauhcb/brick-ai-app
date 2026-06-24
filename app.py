from flask import Flask, render_template_string, request, redirect, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import requests
from datetime import datetime
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'brick_ai_super_secret_key_123')

# Database helper functions
def get_db():
    conn = sqlite3.connect('brick_ai.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # Create tables
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
    
    conn.commit()
    conn.close()
    print("✅ Database initialized!")

# Initialize database
init_db()

# Try importing optional packages
try:
    import wikipedia
except ImportError:
    wikipedia = None

try:
    from googlesearch import search as google_search
except ImportError:
    google_search = None

# Gemini AI (optional)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
gemini_client = None

def init_gemini():
    global gemini_client
    if not GEMINI_API_KEY:
        return
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_client = genai.GenerativeModel('gemini-1.5-flash')
        print("✅ Gemini AI initialized")
    except:
        print("⚠️ Gemini not available")

init_gemini()

def query_gemini(prompt):
    if not gemini_client:
        return None
    try:
        response = gemini_client.generate_content(prompt)
        return response.text
    except:
        return None

# Search Functions
def search_google(query):
    if not google_search:
        return []
    try:
        results = []
        for url in google_search(query, num_results=3):
            results.append(url)
        return results
    except:
        return []

def search_bing(query):
    try:
        bing_api_key = os.environ.get("BING_API_KEY", "")
        if bing_api_key:
            headers = {"Ocp-Apim-Subscription-Key": bing_api_key}
            params = {"q": query, "mkt": "en-us"}
            response = requests.get("https://api.bing.microsoft.com/v7.0/search", headers=headers, params=params)
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
                summary = wikipedia.summary(title, sentences=2)
                summaries.append({'title': title, 'summary': summary, 'url': page.url})
            except:
                continue
        return summaries
    except:
        return []

def smart_search(query):
    result = query_gemini(f"Provide a concise answer to: {query}")
    return result if result else "AI search unavailable"

def summarize_content(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        text = response.text[:500]
        return text[:200] + "..."
    except:
        return "Unable to fetch content"

# Templates
MAIN_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BRICK AI - Search</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: {% if session.get('theme') == 'dark' %}linear-gradient(135deg, #1e3c72 0%, #2a5298 100%){% else %}linear-gradient(135deg, #667eea 0%, #764ba2 100%){% endif %};
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 900px; margin: 0 auto; }
        .header {
            background: rgba(255,255,255,0.95);
            padding: 20px;
            border-radius: 15px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .header h1 { color: #667eea; font-size: 28px; }
        .header-buttons { display: flex; gap: 10px; }
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
        .btn-icon:hover { background: #5a6fd6; }
        .search-box {
            background: rgba(255,255,255,0.95);
            padding: 25px;
            border-radius: 15px;
            margin-bottom: 20px;
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
        .mode-btn.active { background: #667eea; color: white; }
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
        .search-btn:hover { background: #5a6fd6; }
        .results-container {
            background: rgba(255,255,255,0.95);
            padding: 25px;
            border-radius: 15px;
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
        .source-icon { font-size: 24px; }
        .result-item {
            margin-bottom: 15px;
            padding: 15px;
            background: white;
            border-radius: 8px;
        }
        .result-title { font-weight: bold; color: #333; margin-bottom: 8px; }
        .result-summary { color: #666; line-height: 1.6; }
        .result-link {
            color: #667eea;
            text-decoration: none;
            font-size: 14px;
            margin-top: 8px;
            display: inline-block;
        }
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
        
        <div class="search-box">
            <input type="text" class="search-input" id="searchQuery" placeholder="What would you like to search?" value="{{ query if query else '' }}">
            <div class="search-mode">
                <button class="mode-btn active" onclick="setMode('all')">🔍 All</button>
                <button class="mode-btn" onclick="setMode('google')">🌐 Google</button>
                <button class="mode-btn" onclick="setMode('bing')">🔎 Bing</button>
                <button class="mode-btn" onclick="setMode('wiki')">📚 Wikipedia</button>
                <button class="mode-btn" onclick="setMode('ai')">🤖 AI</button>
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
                <br><small style="color: #666;">{{ item.timestamp }}</small>
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
        }
        function performSearch() {
            const query = document.getElementById('searchQuery').value;
            if (!query.trim()) { alert('Please enter a search query'); return; }
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
                    if (response.ok) alert('Thank you for your feedback!');
                });
            }
        }
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
    <title>Settings - BRICK AI</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: {% if session.get('theme') == 'dark' %}linear-gradient(135deg, #1e3c72 0%, #2a5298 100%){% else %}linear-gradient(135deg, #667eea 0%, #764ba2 100%){% endif %};
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 600px; margin: 0 auto; }
        .settings-card {
            background: rgba(255,255,255,0.95);
            padding: 30px;
            border-radius: 15px;
        }
        h1 { color: #667eea; text-align: center; margin-bottom: 25px; }
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
        }
        .theme-btn.active { border-color: #667eea; background: #f8f9ff; }
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
            <h1>⚙️ Settings</h1>
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
            background: rgba(255,255,255,0.95);
            padding: 40px;
            border-radius: 15px;
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
            background: rgba(255,255,255,0.95);
            padding: 40px;
            border-radius: 15px;
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
        
        # Check if user exists
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
    
    if not query:
        flash('Please enter a search query.', 'error')
        return redirect('/dashboard')
    
    html_parts = []
    
    # Google Search
    if mode in ['all', 'google']:
        google_results = search_google(query)
        if google_results:
            html_parts.append('<div class="source-section">')
            html_parts.append('<div class="source-header"><span class="source-icon">🌐</span> Google</div>')
            for i, url in enumerate(google_results[:3], 1):
                summary = summarize_content(url)
                html_parts.append(f'''
                <div class="result-item">
                    <div class="result-title">Result {i}</div>
                    <div class="result-summary">{summary}</div>
                    <a href="{url}" target="_blank" class="result-link">→ View</a>
                </div>
                ''')
            html_parts.append('</div>')
    
    # Bing Search
    if mode in ['all', 'bing']:
        bing_results = search_bing(query)
        if bing_results:
            html_parts.append('<div class="source-section">')
            html_parts.append('<div class="source-header"><span class="source-icon">🔎</span> Bing</div>')
            for i, url in enumerate(bing_results[:3], 1):
                summary = summarize_content(url)
                html_parts.append(f'''
                <div class="result-item">
                    <div class="result-title">Result {i}</div>
                    <div class="result-summary">{summary}</div>
                    <a href="{url}" target="_blank" class="result-link">→ View</a>
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
                    <a href="{item['url']}" target="_blank" class="result-link">→ Read More</a>
                </div>
                ''')
            html_parts.append('</div>')
    
    # AI Search
    if mode in ['all', 'ai']:
        ai_result = smart_search(query)
        if ai_result and ai_result != "AI search unavailable":
            html_parts.append('<div class="source-section">')
            html_parts.append('<div class="source-header"><span class="source-icon">🤖</span> AI Smart Summary</div>')
            html_parts.append(f'<div class="result-item"><div class="result-summary">{ai_result}</div></div>')
            html_parts.append('</div>')
    
    result_html = ''.join(html_parts) if html_parts else '<p>No results found.</p>'
    
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
    
    return render_template_string(MAIN_TEMPLATE, result=result_html, query=query, history=history)

@app.route('/settings')
def settings():
    if 'user_id' not in session:
        flash('Please login first.', 'error')
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