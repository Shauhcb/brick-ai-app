from flask import Flask, render_template_string, request, redirect, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-123')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///brick_ai.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SearchHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    query = db.Column(db.String(500))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# Create tables
with app.app_context():
    db.create_all()

# Templates
LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head><title>Login - BRICK AI</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Arial;background:linear-gradient(135deg,#667eea,#764ba2);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.box{background:white;padding:40px;border-radius:15px;width:100%;max-width:400px}
h1{color:#667eea;text-align:center;margin-bottom:10px}
.subtitle{text-align:center;color:#666;margin-bottom:30px}
.input-group{margin-bottom:20px}
label{display:block;margin-bottom:8px;color:#333;font-weight:500}
input{width:100%;padding:12px;border:2px solid #e0e0e0;border-radius:8px;font-size:16px}
input:focus{outline:none;border-color:#667eea}
.btn{width:100%;padding:14px;background:#667eea;color:white;border:none;border-radius:8px;font-size:16px;font-weight:bold;cursor:pointer}
.btn:hover{background:#5a6fd6}
.flash{padding:12px;border-radius:8px;margin-bottom:20px;text-align:center}
.error{background:#fee;color:#c00;border:1px solid #fcc}
.success{background:#efe;color:#080;border:1px solid #cfc}
.links{text-align:center;margin-top:20px}
.links a{color:#667eea;text-decoration:none}
</style>
</head>
<body>
<div class="box">
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
<head><title>Register - BRICK AI</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Arial;background:linear-gradient(135deg,#667eea,#764ba2);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.box{background:white;padding:40px;border-radius:15px;width:100%;max-width:400px}
h1{color:#667eea;text-align:center;margin-bottom:10px}
.subtitle{text-align:center;color:#666;margin-bottom:30px}
.input-group{margin-bottom:20px}
label{display:block;margin-bottom:8px;color:#333;font-weight:500}
input{width:100%;padding:12px;border:2px solid #e0e0e0;border-radius:8px;font-size:16px}
input:focus{outline:none;border-color:#667eea}
.btn{width:100%;padding:14px;background:#667eea;color:white;border:none;border-radius:8px;font-size:16px;font-weight:bold;cursor:pointer}
.btn:hover{background:#5a6fd6}
.flash{padding:12px;border-radius:8px;margin-bottom:20px;text-align:center}
.error{background:#fee;color:#c00;border:1px solid #fcc}
.success{background:#efe;color:#080;border:1px solid #cfc}
.links{text-align:center;margin-top:20px}
.links a{color:#667eea;text-decoration:none}
</style>
</head>
<body>
<div class="box">
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

DASHBOARD_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head><title>BRICK AI - Search</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Arial;background:linear-gradient(135deg,#667eea,#764ba2);min-height:100vh;padding:20px}
.container{max-width:900px;margin:0 auto}
.header{background:white;padding:20px;border-radius:15px;margin-bottom:20px;display:flex;justify-content:space-between;align-items:center}
.header h1{color:#667eea}
.btn{padding:10px 20px;background:#667eea;color:white;border:none;border-radius:8px;cursor:pointer;text-decoration:none}
.btn:hover{background:#5a6fd6}
.btn-danger{background:#e74c3c}
.btn-danger:hover{background:#c0392b}
.search-box{background:white;padding:25px;border-radius:15px;margin-bottom:20px}
.search-input{width:100%;padding:15px;border:2px solid #e0e0e0;border-radius:10px;font-size:16px;margin-bottom:15px}
.search-btn{width:100%;padding:15px;background:#667eea;color:white;border:none;border-radius:10px;font-size:18px;font-weight:bold;cursor:pointer}
.search-btn:hover{background:#5a6fd6}
.results{background:white;padding:25px;border-radius:15px;margin-bottom:20px}
.history{background:white;padding:25px;border-radius:15px}
.history-item{padding:12px;margin-bottom:10px;background:#f8f9ff;border-radius:8px}
.flash{padding:12px;border-radius:8px;margin-bottom:20px}
.error{background:#fee;color:#c00;border:1px solid #fcc}
.success{background:#efe;color:#080;border:1px solid #cfc}
</style>
</head>
<body>
<div class="container">
{% with messages = get_flashed_messages(with_categories=true) %}
{% for category, message in messages %}
<div class="flash {{ category }}">{{ message }}</div>
{% endfor %}
{% endwith %}

<div class="header">
<h1>👾 BRICK AI</h1>
<div>
<a href="/settings" class="btn">⚙️ Settings</a>
<a href="/logout" class="btn btn-danger">🚪 Logout</a>
</div>
</div>

<div class="search-box">
<form action="/search" method="GET">
<input type="text" name="query" class="search-input" placeholder="What would you like to search?" value="{{ query or '' }}">
<button type="submit" class="search-btn">🚀 Search Now</button>
</form>
</div>

{% if result %}
<div class="results">{{ result|safe }}</div>
{% endif %}

{% if history %}
<div class="history">
<h2 style="color:#667eea;">📜 Recent Searches</h2>
{% for item in history %}
<div class="history-item">
<strong>{{ item.query }}</strong><br>
<small style="color:#666;">{{ item.timestamp.strftime('%Y-%m-%d %H:%M') }}</small>
</div>
{% endfor %}
</div>
{% endif %}
</div>
</body>
</html>
'''

SETTINGS_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head><title>Settings - BRICK AI</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Arial;background:linear-gradient(135deg,#667eea,#764ba2);min-height:100vh;padding:20px}
.container{max-width:600px;margin:0 auto}
.box{background:white;padding:30px;border-radius:15px}
h1{color:#667eea;text-align:center;margin-bottom:25px}
.back{display:inline-block;margin-bottom:20px;color:#667eea;text-decoration:none}
.info{background:#f8f9ff;padding:15px;border-radius:8px;margin-bottom:20px}
.item{margin-bottom:25px;padding-bottom:20px;border-bottom:1px solid #e0e0e0}
.btn{padding:12px 20px;background:#e74c3c;color:white;border:none;border-radius:8px;cursor:pointer;text-decoration:none;display:inline-block}
.btn:hover{background:#c0392b}
.flash{padding:12px;border-radius:8px;margin-bottom:20px}
.error{background:#fee;color:#c00;border:1px solid #fcc}
.success{background:#efe;color:#080;border:1px solid #cfc}
</style>
</head>
<body>
<div class="container">
{% with messages = get_flashed_messages(with_categories=true) %}
{% for category, message in messages %}
<div class="flash {{ category }}">{{ message }}</div>
{% endfor %}
{% endwith %}

<a href="/dashboard" class="back">← Back to Home</a>
<div class="box">
<h1>⚙️ Settings</h1>
<div class="info">
<strong>👤 Logged in as:</strong> {{ session.get('username') }}<br>
<strong>📧 Email:</strong> {{ session.get('user_email') }}
</div>
<div class="item">
<strong>📊 Account Stats</strong>
<p>Total Searches: {{ search_count }}</p>
<p>Member Since: {{ user.created_at.strftime('%B %Y') if user else 'N/A' }}</p>
</div>
<div class="item">
<strong>🔐 Account</strong><br><br>
<a href="/logout" class="btn">🚪 Logout</a>
</div>
</div>
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
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['user_email'] = user.email
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
        
        session['user_id'] = new_user.id
        session['username'] = new_user.username
        session['user_email'] = new_user.email
        
        flash('Account created successfully!', 'success')
        return redirect('/dashboard')
    
    return render_template_string(REGISTER_TEMPLATE)

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Please login first.', 'error')
        return redirect('/login')
    
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect('/login')
    
    history = SearchHistory.query.filter_by(user_id=session['user_id']).order_by(
        SearchHistory.timestamp.desc()
    ).limit(10).all()
    
    return render_template_string(DASHBOARD_TEMPLATE, result='', query='', history=history)

@app.route('/search')
def search():
    if 'user_id' not in session:
        flash('Please login first.', 'error')
        return redirect('/login')
    
    query = request.args.get('query', '')
    if not query:
        flash('Please enter a search query.', 'error')
        return redirect('/dashboard')
    
    result_html = f'''
    <h2 style="color:#667eea;">🔍 Results for: "{query}"</h2>
    <div style="padding:20px; background:#f8f9ff; border-radius:8px; margin-top:15px;">
        <p><strong>📝 Search Results:</strong></p>
        <p>Your search for "<strong>{query}</strong>" was successful!</p>
        <p style="color:#666; margin-top:10px;">Full search features coming soon!</p>
    </div>
    '''
    
    new_search = SearchHistory(user_id=session['user_id'], query=query)
    db.session.add(new_search)
    db.session.commit()
    
    history = SearchHistory.query.filter_by(user_id=session['user_id']).order_by(
        SearchHistory.timestamp.desc()
    ).limit(10).all()
    
    return render_template_string(DASHBOARD_TEMPLATE, result=result_html, query=query, history=history)

@app.route('/settings')
def settings():
    if 'user_id' not in session:
        flash('Please login first.', 'error')
        return redirect('/login')
    
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect('/login')
    
    search_count = SearchHistory.query.filter_by(user_id=user.id).count()
    return render_template_string(SETTINGS_TEMPLATE, user=user, search_count=search_count)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect('/login')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)