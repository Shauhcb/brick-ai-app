from flask import Flask, render_template, request, redirect, session, flash, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import requests
from datetime import datetime
import json
import urllib.parse
import re
from functools import wraps
from time import time
from collections import defaultdict
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24).hex())
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# Configure logging
if not app.debug:
    handler = RotatingFileHandler('brick_ai.log', maxBytes=10000, backupCount=3)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

# Database configuration
DB_PATH = os.environ.get('DATABASE_PATH', 'brick_ai.db')
if os.environ.get('RENDER'):
    import os
    from pathlib import Path
    Path('/var/data').mkdir(parents=True, exist_ok=True)
    DB_PATH = '/var/data/brick_ai.db'

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        theme TEXT DEFAULT 'light',
        language TEXT DEFAULT 'en',
        notifications BOOLEAN DEFAULT 1,
        last_login TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS search_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        query TEXT NOT NULL,
        result TEXT,
        mode TEXT,
        response_time INTEGER,
        ip_address TEXT,
        user_agent TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        response TEXT NOT NULL,
        intent TEXT,
        response_time INTEGER,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        category TEXT DEFAULT 'general',
        message TEXT NOT NULL,
        rating INTEGER CHECK(rating >= 1 AND rating <= 5),
        status TEXT DEFAULT 'pending',
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS api_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        endpoint TEXT NOT NULL,
        request_count INTEGER DEFAULT 0,
        total_tokens INTEGER DEFAULT 0,
        date DATE DEFAULT CURRENT_DATE,
        FOREIGN KEY (user_id) REFERENCES users (id))''')
    
    # Create indexes for performance
    c.execute('CREATE INDEX IF NOT EXISTS idx_search_user_timestamp ON search_history(user_id, timestamp)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_chat_user_timestamp ON chat_messages(user_id, timestamp)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_feedback_user ON feedback(user_id)')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized!")

init_db()

# Rate limiting
RATE_LIMIT = {
    'chat': {'requests': 20, 'period': 60},
    'search': {'requests': 10, 'period': 60},
}

rate_limit_storage = defaultdict(list)

def rate_limit(limit_key='default'):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return f(*args, **kwargs)
            
            user_id = session['user_id']
            key = f"{user_id}:{limit_key}"
            now = time()
            
            rate_limit_storage[key] = [t for t in rate_limit_storage[key] if t > now - RATE_LIMIT[limit_key]['period']]
            
            if len(rate_limit_storage[key]) >= RATE_LIMIT[limit_key]['requests']:
                return jsonify({'error': 'Rate limit exceeded. Please wait a moment.'}), 429
            
            rate_limit_storage[key].append(now)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# AI Client Setup
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
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
    if gemini_client:
        try:
            response = gemini_client.generate_content(prompt)
            if response and response.text:
                return response.text
        except Exception as e:
            print(f"Gemini error: {e}")
    
    # Fallback responses
    prompt_lower = prompt.lower()
    if any(w in prompt_lower for w in ['hello', 'hi', 'hey']):
        return "Hello there! 👋 I'm BRICK AI."
    if 'help' in prompt_lower:
        return "I can help you with answering questions, searching the web, or just chatting!"
    if 'time' in prompt_lower:
        return f"The current time is {datetime.now().strftime('%I:%M %p')} 📅"
    return f"🤖 BRICK AI here! I understand you're asking about: '{prompt}'."

def search_web(query):
    try:
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://api.duckduckgo.com/?q={encoded_query}&format=json&no_html=1&skip_disambig=1"
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if response.status_code == 200:
            data = response.json()
            results = []
            if data.get('AbstractText'):
                results.append({
                    'title': data.get('Heading', query),
                    'summary': data.get('AbstractText', ''),
                    'url': data.get('AbstractURL', '')
                })
            if data.get('RelatedTopics'):
                for topic in data['RelatedTopics'][:5]:
                    if 'Text' in topic:
                        text = re.sub(r'<[^>]+>', '', topic['Text'])
                        url_match = re.search(r'https?://[^\s]+', text)
                        url = url_match.group(0) if url_match else ''
                        text = re.sub(r'https?://[^\s]+', '', text).strip()
                        if text and len(text) > 10:
                            results.append({
                                'title': text[:50],
                                'summary': text[:200],
                                'url': url
                            })
            return results
    except Exception as e:
        print(f"Web search error: {e}")
    return []

def search_wikipedia(query):
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
                    results.append({
                        'title': title,
                        'summary': f"Wikipedia article about {title}",
                        'url': f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
                    })
            return results
    except Exception as e:
        print(f"Wikipedia error: {e}")
    return []

# Routes
@app.route('/')
def index():
    return redirect('/dashboard' if 'user_id' in session else '/login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect('/dashboard')
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['user_email'] = user['email']
            session['theme'] = user['theme'] or 'light'
            # Update last login
            db.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?', (user['id'],))
            db.commit()
            flash('Logged in successfully!', 'success')
            return redirect('/dashboard')
        flash('Invalid email or password!', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect('/dashboard')
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        db = get_db()
        if db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone():
            flash('Email already registered!', 'error')
        elif db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone():
            flash('Username already taken!', 'error')
        else:
            db.execute('INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
                       (username, email, generate_password_hash(password)))
            db.commit()
            flash('Account created! Please login.', 'success')
            return redirect('/login')
    return render_template('register.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')
    return render_template('dashboard.html')

@app.route('/search', methods=['GET', 'POST'])
@rate_limit('search')
def search():
    if 'user_id' not in session:
        return redirect('/login')
    db = get_db()
    
    if request.method == 'POST':
        query = request.form.get('query', '')
        mode = request.form.get('mode', 'all')
        if not query:
            return redirect('/search')
        
        start_time = time()
        results_data = {'web': [], 'wiki': [], 'ai': ''}
        
        if mode in ['all', 'google', 'bing']:
            results_data['web'] = search_web(query)
        if mode in ['all', 'wiki']:
            results_data['wiki'] = search_wikipedia(query)
        if mode in ['all', 'ai']:
            results_data['ai'] = get_ai_response(f"Provide a comprehensive answer to: {query}")
        
        response_time = int((time() - start_time) * 1000)
        
        # Save to history
        summary = f"Web: {len(results_data['web'])}, Wiki: {len(results_data['wiki'])}, AI: {'Yes' if results_data['ai'] else 'No'}"
        db.execute('INSERT INTO search_history (user_id, query, result, mode, response_time) VALUES (?, ?, ?, ?, ?)',
                   (session['user_id'], query, summary, mode, response_time))
        db.commit()
        
        history = db.execute('SELECT * FROM search_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10',
                           (session['user_id'],)).fetchall()
        return render_template('search.html', results_data=results_data, query=query, history=history, mode=mode)
    
    history = db.execute('SELECT * FROM search_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10',
                       (session['user_id'],)).fetchall()
    return render_template('search.html', results_data=None, query='', history=history, mode='all')

@app.route('/chat', methods=['POST'])
@rate_limit('chat')
def chat():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    message = data.get('message', '')
    if not message:
        return jsonify({'error': 'No message provided'}), 400
    
    start_time = time()
    response = get_ai_response(message)
    response_time = int((time() - start_time) * 1000)
    
    db = get_db()
    db.execute('INSERT INTO chat_messages (user_id, message, response, response_time) VALUES (?, ?, ?, ?)',
               (session['user_id'], message, response, response_time))
    db.commit()
    return jsonify({'response': response})

@app.route('/get-chat-history', methods=['GET'])
def get_chat_history():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    db = get_db()
    messages = db.execute('SELECT message, response, timestamp FROM chat_messages WHERE user_id = ? ORDER BY timestamp ASC',
                        (session['user_id'],)).fetchall()
    return jsonify({'history': [dict(msg) for msg in messages]})

@app.route('/clear-chat', methods=['POST'])
def clear_chat():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    db = get_db()
    db.execute('DELETE FROM chat_messages WHERE user_id = ?', (session['user_id'],))
    db.commit()
    return jsonify({'success': True})

@app.route('/settings')
def settings():
    if 'user_id' not in session:
        return redirect('/login')
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if not user:
        return redirect('/login')
    
    search_count = db.execute('SELECT COUNT(*) FROM search_history WHERE user_id = ?',
                            (session['user_id'],)).fetchone()[0]
    chat_count = db.execute('SELECT COUNT(*) FROM chat_messages WHERE user_id = ?',
                          (session['user_id'],)).fetchone()[0]
    feedback_count = db.execute('SELECT COUNT(*) FROM feedback WHERE user_id = ?',
                              (session['user_id'],)).fetchone()[0]
    
    return render_template('settings.html', user=user, search_count=search_count,
                         chat_count=chat_count, feedback_count=feedback_count)

@app.route('/set-theme', methods=['POST'])
def set_theme():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    theme = request.get_json().get('theme', 'light')
    db = get_db()
    db.execute('UPDATE users SET theme = ? WHERE id = ?', (theme, session['user_id']))
    db.commit()
    session['theme'] = theme
    return jsonify({'success': True})

@app.route('/submit-feedback', methods=['POST'])
def submit_feedback():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    message = request.get_json().get('message', '')
    if message:
        db = get_db()
        db.execute('INSERT INTO feedback (user_id, message) VALUES (?, ?)',
                  (session['user_id'], message))
        db.commit()
        return jsonify({'success': True})
    return jsonify({'error': 'No message provided'}), 400

@app.route('/admin/stats')
def admin_stats():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    # Check if user is admin (you can set this up)
    # For now, just show basic stats
    db = get_db()
    stats = {
        'total_users': db.execute('SELECT COUNT(*) FROM users').fetchone()[0],
        'total_searches': db.execute('SELECT COUNT(*) FROM search_history').fetchone()[0],
        'total_chats': db.execute('SELECT COUNT(*) FROM chat_messages').fetchone()[0],
        'active_users_today': db.execute('''
            SELECT COUNT(DISTINCT user_id) FROM search_history 
            WHERE date(timestamp) = date('now')
        ''').fetchone()[0],
        'feedback_count': db.execute('SELECT COUNT(*) FROM feedback').fetchone()[0]
    }
    return jsonify(stats)

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db = get_db()
    db.rollback()
    flash('An unexpected error occurred. Our team has been notified.', 'error')
    return render_template('error.html', error=str(error)), 500

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect('/login')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)