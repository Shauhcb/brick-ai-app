from flask import Flask, render_template_string, request, redirect, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import requests
from datetime import datetime
import json
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
        notifications BOOLEAN DEFAULT 1,
        language TEXT DEFAULT 'en',
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
    
    c.execute('''CREATE TABLE IF NOT EXISTS user_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL UNIQUE,
        auto_save_chats BOOLEAN DEFAULT 1,
        show_timestamps BOOLEAN DEFAULT 1,
        search_suggestions BOOLEAN DEFAULT 1,
        dark_mode BOOLEAN DEFAULT 0,
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
    print("✅ Wikipedia loaded")
except ImportError:
    wikipedia = None
    print("⚠️ Wikipedia not available")

try:
    from googlesearch import search as google_search
    print("✅ Google search loaded")
except ImportError:
    google_search = None
    print("⚠️ Google search not available")

# Get API keys
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
HUGGINGFACE_API_KEY = os.environ.get("HUGGINGFACE_API_KEY", "")

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
    # Try Gemini first
    if gemini_client:
        try:
            response = gemini_client.generate_content(prompt)
            if response and response.text:
                return response.text
        except Exception as e:
            print(f"Gemini error: {e}")
    
    # Try HuggingFace as fallback
    if HUGGINGFACE_API_KEY:
        try:
            API_URL = "https://api-inference.huggingface.co/models/microsoft/DialoGPT-medium"
            headers = {"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"}
            payload = {"inputs": prompt}
            response = requests.post(API_URL, headers=headers, json=payload, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data and isinstance(data, list) and len(data) > 0:
                    return data[0].get('generated_text', prompt)
        except Exception as e:
            print(f"HuggingFace error: {e}")
    
    # Simple fallback responses
    return "I'm BRICK AI! 😊 How can I help you today?"

# Search Functions
def search_google(query):
    if not google_search:
        return []
    try:
        results = []
        for url in google_search(query, num_results=5, stop=5, pause=2):
            results.append(url)
        return results
    except Exception as e:
        print(f"Google search error: {e}")
        return []

def search_bing(query):
    try:
        bing_key = os.environ.get("BING_API_KEY", "")
        if bing_key:
            headers = {"Ocp-Apim-Subscription-Key": bing_key}
            params = {"q": query, "count": 3, "mkt": "en-US"}
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

# Templates - Only the settings template is updated, others remain the same
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
        h1 { 
            text-align: center; 
            margin-bottom: 25px;
            color: #667eea;
            font-size: 28px;
        }
        .setting-item {
            margin-bottom: 25px;
            padding-bottom: 20px;
            border-bottom: 1px solid #e0e0e0;
        }
        .setting-item:last-child { border-bottom: none; }
        .setting-label { 
            font-weight: bold; 
            color: #333; 
            margin-bottom: 10px; 
            display: block;
            font-size: 16px;
        }
        .setting-desc {
            color: #666;
            font-size: 13px;
            margin-top: 5px;
        }
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
            gap: 15px;
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
        .toggle.active {
            background: #667eea;
        }
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
        .toggle.active .slider {
            left: 25px;
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
        .user-info p {
            margin: 5px 0;
            color: #333;
        }
        .user-info strong { color: #667eea; }
        .stats-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }
        .stat-box {
            background: #f8f9ff;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }
        .stat-box .number {
            font-size: 24px;
            font-weight: bold;
            color: #667eea;
        }
        .stat-box .label {
            color: #666;
            font-size: 13px;
            margin-top: 5px;
        }
        .flash-messages { margin-bottom: 20px; }
        .flash {
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 10px;
        }
        .flash.error { background: #fee; color: #c00; border: 1px solid #fcc; }
        .flash.success { background: #efe; color: #080; border: 1px solid #cfc; }
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
        
        <a href="/dashboard" class="back-btn">← Back to Home</a>
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
                <div class="setting-desc">Save all chat conversations automatically</div>
                <br>
                <div class="toggle-container">
                    <span>Show timestamps</span>
                    <div class="toggle active" onclick="toggleSetting('timestamps')">
                        <div class="slider"></div>
                    </div>
                </div>
                <div class="setting-desc">Display time on each message</div>
            </div>
            
            <div class="setting-item">
                <span class="setting-label">🔍 Search Settings</span>
                <div class="toggle-container">
                    <span>Enable search suggestions</span>
                    <div class="toggle active" onclick="toggleSetting('suggestions')">
                        <div class="slider"></div>
                    </div>
                </div>
                <div class="setting-desc">Show suggestions while typing</div>
            </div>
            
            <div class="setting-item">
                <span class="setting-label">📊 Account Statistics</span>
                <div class="stats-grid">
                    <div class="stat-box">
                        <div class="number">{{ search_count }}</div>
                        <div class="label">Total Searches</div>
                    </div>
                    <div class="stat-box">
                        <div class="number">{{ chat_count }}</div>
                        <div class="label">Chat Messages</div>
                    </div>
                    <div class="stat-box">
                        <div class="number">{{ feedback_count }}</div>
                        <div class="label">Feedback Sent</div>
                    </div>
                    <div class="stat-box">
                        <div class="number">{{ days_active }}</div>
                        <div class="label">Days Active</div>
                    </div>
                </div>
            </div>
            
            <div class="setting-item">
                <span class="setting-label">📝 Data Management</span>
                <button class="logout-btn" style="background: #f39c12; margin-bottom: 10px;" onclick="clearHistory()">🗑️ Clear Search History</button>
                <button class="logout-btn" style="background: #3498db; margin-bottom: 10px;" onclick="exportData()">📤 Export My Data</button>
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
            // Save setting to server
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
                }).then(() => location.reload());
            }
        }
        
        function exportData() {
            window.location.href = '/export-data';
        }
    </script>
</body>
</html>
'''

# Keep all other templates (LOGIN_TEMPLATE, REGISTER_TEMPLATE, MAIN_TEMPLATE) from the previous working version

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
    
    # Get chat messages for the chat tab
    c.execute('SELECT * FROM chat_messages WHERE user_id = ? ORDER BY timestamp DESC LIMIT 50', (session['user_id'],))
    chat_history = c.fetchall()
    conn.close()
    
    # Convert chat history to JSON for JavaScript
    chat_history_json = []
    for msg in chat_history:
        chat_history_json.append({
            'message': msg['message'],
            'response': msg['response'],
            'timestamp': msg['timestamp']
        })
    
    return render_template_string(MAIN_TEMPLATE, result='', query='', history=history, chat_history=chat_history_json)

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
                <div class="result-item">No Google results found for "{query}". Try a different search.</div>
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
        try:
            ai_result = get_ai_response(f"Provide a comprehensive answer to: {query}")
            if ai_result:
                html_parts.append('<div class="source-section">')
                html_parts.append('<div class="source-header"><span class="source-icon">🤖</span> AI Smart Summary</div>')
                html_parts.append(f'<div class="result-item"><div class="result-summary">{ai_result}</div></div>')
                html_parts.append('</div>')
        except Exception as e:
            html_parts.append(f'''
            <div class="source-section">
                <div class="source-header"><span class="source-icon">🤖</span> AI Smart Summary</div>
                <div class="result-item">AI search is currently unavailable. Please try again later.</div>
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
    
    # Get AI response
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
    chat_count = c.execute('SELECT COUNT(*) FROM chat_messages WHERE user_id = ?', (session['user_id'],)).fetchone()[0]
    feedback_count = c.execute('SELECT COUNT(*) FROM feedback WHERE user_id = ?', (session['user_id'],)).fetchone()[0]
    
    # Calculate days active
    created_at = datetime.strptime(user['created_at'], '%Y-%m-%d %H:%M:%S')
    days_active = (datetime.now() - created_at).days
    
    conn.close()
    
    return render_template_string(SETTINGS_TEMPLATE, 
                                 user=user, 
                                 search_count=search_count,
                                 chat_count=chat_count,
                                 feedback_count=feedback_count,
                                 days_active=days_active,
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
    
    # Store settings in session or database
    if setting == 'auto_save':
        session['auto_save_chats'] = value
    elif setting == 'timestamps':
        session['show_timestamps'] = value
    elif setting == 'suggestions':
        session['search_suggestions'] = value
    
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
    
    flash('Search history cleared!', 'success')
    return jsonify({'success': True})

@app.route('/export-data', methods=['GET'])
def export_data():
    if 'user_id' not in session:
        flash('Please login first.', 'error')
        return redirect('/login')
    
    conn = get_db()
    c = conn.cursor()
    
    # Get all user data
    c.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
    user = c.fetchone()
    
    c.execute('SELECT * FROM search_history WHERE user_id = ?', (session['user_id'],))
    searches = c.fetchall()
    
    c.execute('SELECT * FROM chat_messages WHERE user_id = ?', (session['user_id'],))
    chats = c.fetchall()
    
    c.execute('SELECT * FROM feedback WHERE user_id = ?', (session['user_id'],))
    feedbacks = c.fetchall()
    
    conn.close()
    
    # Create JSON export
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

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect('/login')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)