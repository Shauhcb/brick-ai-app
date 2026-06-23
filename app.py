from flask import Flask, render_template_string, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
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
    try:
        results = []
        for url in google_search(query, num_results=3):
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
            params = {"q": query, "mkt": "en-us"}
            endpoint = "https://api.bing.microsoft.com/v7.0/search"
            response = requests.get(endpoint, headers=headers, params=params)
            data = response.json()
            return [result['url'] for result in data.get('webPages', {}).get('value', [])[:3]]
        else:
            return ["Bing API key not configured"]
    except Exception as e:
        print(f"Bing search error: {e}")
        return []

def search_wikipedia(query):
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
    prompt = f"""Provide a comprehensive answer to this query: {query}
    
    Include:
    - Key facts
    - Important details
    - Related information
    
    Keep it concise but informative."""
    
    result = query_gemini(prompt)
    return result if result else "Smart search unavailable"

def summarize_content(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        text = response.text[:2000]
        prompt = f"Summarize this content in 2-3 sentences:\n\n{text[:500]}"
        summary = query_gemini(prompt)
        return summary if summary else text[:300] + "..."
    except Exception as e:
        print(f"Summarization error: {e}")
        return "Unable to fetch content"

# [INSERT ALL YOUR TEMPLATES HERE - MAIN_APP_TEMPLATE, SETTINGS_TEMPLATE, LOGIN_TEMPLATE, REGISTER_TEMPLATE]
# Note: Keep the template strings as they are in your original code

# Routes
@app.route('/')
def index():
    return redirect(url_for('home'))

@app.route("/login", methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email, auth_provider='local').first()
        
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['theme'] = user.theme
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
        
        flash('Account created successfully! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template_string(REGISTER_TEMPLATE)

@app.route("/logout")
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

@app.route("/settings")
def settings():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    search_count = SearchHistory.query.filter_by(user_id=user.id).count()
    
    return render_template_string(SETTINGS_TEMPLATE, user=user, search_count=search_count)

@app.route('/set-theme', methods=['POST'])
def set_theme():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    data = request.get_json()
    theme = data.get('theme', 'light')
    
    user = User.query.get(session['user_id'])
    user.theme = theme
    session['theme'] = theme
    db.session.commit()
    
    return jsonify({'success': True})

@app.route("/submit-feedback", methods=['POST'])
def submit_feedback():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    data = request.get_json()
    message = data.get('message', '')
    
    if message:
        feedback = Feedback(user_id=session['user_id'], message=message)
        db.session.add(feedback)
        db.session.commit()
    
    return jsonify({'success': True})

@app.route("/", methods=["GET", "POST"])
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
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
def search():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    query = request.args.get('query', '')
    mode = request.args.get('mode', 'all')
    
    if not query:
        return redirect(url_for('home'))
    
    result_html = perform_multi_search(query, mode)
    
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