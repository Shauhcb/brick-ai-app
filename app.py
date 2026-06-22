import os
from flask import Flask, request, render_template_string, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import requests
from markupsafe import escape
import wikipedia
from datetime import datetime
import json
import traceback
import re
import time

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'

# ====== KEYS HARDCODED ======
app.config['SECRET_KEY'] = 'brick_ai_super_secret_key_123'
app.config['DEBUG'] = True

# Replace these with your actual API keys
GEMINI_API_KEY = ""  # Leave empty to use Simple Bot
HUGGINGFACE_API_KEY = ""  # Leave empty to use Simple Bot
# ============================

db = SQLAlchemy(app)

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
            print("✅ Gemini AI initialized with deprecated client")
        except ImportError:
            print("❌ Google Generative AI package not installed")
        except Exception as e:
            print(f"❌ Failed to initialize Gemini (old client): {e}")
    except Exception as e:
        print(f"❌ Failed to initialize Gemini (new client): {e}")

init_gemini()

# HuggingFace Configuration
HUGGINGFACE_MODEL = "microsoft/DialoGPT-medium"
HUGGINGFACE_API_URL = "https://api-inference.huggingface.co/models/" + HUGGINGFACE_MODEL

if HUGGINGFACE_API_KEY and HUGGINGFACE_API_KEY != "":
    print("✅ HuggingFace API configured")
else:
    print("⚠️ HuggingFace API key not set - using Simple Bot only")

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=True)
    email = db.Column(db.String(150), unique=True, nullable=True)
    phone = db.Column(db.String(20), unique=True, nullable=True)
    password_hash = db.Column(db.String(200), nullable=True)
    auth_provider = db.Column(db.String(50), default='local')
    provider_id = db.Column(db.String(200), nullable=True)
    is_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SearchHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    search_query = db.Column(db.Text, nullable=False)
    mode = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=False)
    chatbot = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# Helper function for Gemini API calls
def get_gemini_response(prompt):
    if not gemini_client:
        return None, "Gemini client not initialized"
    
    try:
        if USE_OLD_GEMINI:
            response = gemini_client.generate_content(prompt)
            return response.text, None
        else:
            response = gemini_client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt
            )
            return response.text, None
    except Exception as e:
        error_msg = str(e)
        print(f"Gemini API error: {error_msg}")
        return None, f"Gemini Error: {error_msg}"

# HuggingFace API function with better error handling
def get_huggingface_response(prompt):
    if not HUGGINGFACE_API_KEY or HUGGINGFACE_API_KEY == "":
        return None, "HuggingFace API key not configured"
    
    try:
        headers = {
            "Authorization": f"Bearer {HUGGINGFACE_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_length": 100,
                "temperature": 0.7,
                "do_sample": True,
                "top_p": 0.95,
                "pad_token_id": 50256
            }
        }
        
        response = requests.post(HUGGINGFACE_API_URL, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            try:
                result = response.json()
                if isinstance(result, list) and len(result) > 0:
                    if 'generated_text' in result[0]:
                        generated_text = result[0]['generated_text']
                        if generated_text.startswith(prompt):
                            generated_text = generated_text[len(prompt):].strip()
                        return generated_text, None
                return str(result), None
            except json.JSONDecodeError:
                return None, f"Invalid JSON response"
        else:
            return None, f"HTTP {response.status_code}"
    except requests.exceptions.Timeout:
        return None, "HuggingFace API timeout"
    except Exception as e:
        return None, f"HuggingFace Error: {str(e)}"

# Enhanced AI function with better fallbacks
def get_ai_response(prompt, prefer_gemini=True):
    # Try Gemini first if preferred and available
    if prefer_gemini and gemini_client:
        response, error = get_gemini_response(prompt)
        if response:
            return response, "gemini", None
        print(f"Gemini failed: {error}")
    
    # Try HuggingFace as second option
    if HUGGINGFACE_API_KEY and HUGGINGFACE_API_KEY != "":
        response, error = get_huggingface_response(prompt)
        if response:
            return response, "huggingface", None
        print(f"HuggingFace failed: {error}")
    
    # Use enhanced simple bot
    return enhanced_simple_bot(prompt), "simple", None

def enhanced_simple_bot(message):
    """Enhanced rule-based chatbot with more responses"""
    message = message.lower().strip()
    
    # Greetings
    if any(word in message for word in ['hello', 'hi', 'hey', 'greetings', 'good morning', 'good afternoon', 'good evening']):
        return "Hello! How can I assist you today? 👋"
    
    # How are you
    elif any(word in message for word in ['how are you', 'how do you do', 'how\'s it going']):
        return "I'm doing great! Thanks for asking. How can I help you today? 😊"
    
    # Name
    elif any(word in message for word in ['what is your name', 'who are you', 'your name']):
        return "I'm BRICK AI, your intelligent assistant! 🧠"
    
    # Thanks
    elif any(word in message for word in ['thank', 'thanks', 'thank you']):
        return "You're welcome! Feel free to ask me anything. 🌟"
    
    # Goodbye
    elif any(word in message for word in ['bye', 'goodbye', 'see you', 'later']):
        return "Goodbye! Have a great day! 👋"
    
    # Help
    elif 'help' in message:
        return """I can help you with various topics! Try:
- Asking about science, history, or technology
- Getting Wikipedia summaries
- Smart web searches
- General knowledge questions
    
What would you like to know? 🤔"""
    
    # Weather
    elif 'weather' in message:
        return "I don't have real-time weather data yet. Try checking a weather website! 🌤️"
    
    # Time
    elif 'time' in message:
        now = datetime.now().strftime("%I:%M %p")
        return f"The current time is {now} ⏰"
    
    # Date
    elif 'date' in message or 'today' in message:
        now = datetime.now().strftime("%B %d, %Y")
        return f"Today is {now} 📅"
    
    # Joke
    elif 'joke' in message:
        return "Why don't scientists trust atoms? Because they make up everything! 😄"
    
    # AI/ML
    elif 'ai' in message or 'artificial intelligence' in message:
        return "AI (Artificial Intelligence) is the simulation of human intelligence in machines. I'm a simple AI assistant! 🤖"
    
    # Programming
    elif 'python' in message:
        return "Python is a popular programming language! It's great for web development, data science, AI, and more. 🐍"
    
    # Default response
    else:
        return f"I understand you mentioned '{message}'. I'm a simple bot. For advanced AI responses, please configure your Gemini or HuggingFace API keys. 🔑"

# Wikipedia search with better error handling
def search_wikipedia(query):
    """Search Wikipedia with better error handling"""
    try:
        # Try using the REST API first (more reliable)
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(query)}"
        headers = {'User-Agent': 'BRICK-AI/1.0 (Contact: support@brickai.com)'}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            try:
                data = response.json()
                if data and 'extract' in data and data['extract']:
                    return data['extract'], None
                else:
                    return None, "No information found"
            except json.JSONDecodeError:
                # If JSON parsing fails, fallback to regular Wikipedia
                pass
        
        # Fallback to wikipedia library
        wikipedia.set_lang('en')
        try:
            summary = wikipedia.summary(query, sentences=5, auto_suggest=True)
            return summary, None
        except wikipedia.exceptions.PageError:
            # Try with auto-suggest
            try:
                suggestions = wikipedia.search(query)
                if suggestions:
                    summary = wikipedia.summary(suggestions[0], sentences=3)
                    return f"Did you mean '{suggestions[0]}'? {summary}", None
                else:
                    return None, "No Wikipedia page found"
            except:
                return None, "No Wikipedia page found"
        except wikipedia.exceptions.DisambiguationError as e:
            options = e.options[:5]
            return f"Did you mean: {', '.join(options)}?", None
        except Exception as e:
            return None, f"Error: {str(e)}"
            
    except requests.exceptions.Timeout:
        return None, "Request timed out"
    except requests.exceptions.ConnectionError:
        return None, "Connection error - check your internet"
    except Exception as e:
        return None, f"Error: {str(e)}"

# Validation functions
def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_phone(phone):
    pattern = r'^\+?[1-9]\d{1,14}$'
    return re.match(pattern, phone) is not None

def validate_username(username):
    pattern = r'^[a-zA-Z0-9_]{3,20}$'
    return re.match(pattern, username) is not None

# Templates (shortened for space)
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Login - BRICK AI 👾</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px; }
        .container { background: white; padding: 40px; border-radius: 20px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); width: 100%; max-width: 420px; }
        h1 { color: #333; text-align: center; margin-bottom: 10px; font-size: 2em; }
        .emoji { color: #ff0000; }
        .subtitle { text-align: center; color: #666; margin-bottom: 30px; font-size: 14px; }
        .error { background: #fee; color: #c33; padding: 12px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #c33; }
        .success { background: #efe; color: #3c3; padding: 12px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #3c3; }
        .login-options { display: flex; flex-direction: column; gap: 12px; margin-bottom: 20px; }
        .social-btn { width: 100%; padding: 14px; font-size: 16px; border-radius: 10px; border: none; color: white; cursor: pointer; font-weight: bold; transition: transform 0.2s, box-shadow 0.2s; display: flex; align-items: center; justify-content: center; gap: 10px; }
        .social-btn:hover { transform: translateY(-2px); box-shadow: 0 4px 15px rgba(0,0,0,0.2); }
        .google-btn { background: #db4437; }
        .facebook-btn { background: #1877f2; }
        .phone-btn { background: #25D366; }
        .email-btn { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .divider { display: flex; align-items: center; text-align: center; margin: 20px 0; }
        .divider::before, .divider::after { content: ''; flex: 1; border-bottom: 1px solid #ddd; }
        .divider::before { margin-right: 10px; }
        .divider::after { margin-left: 10px; }
        .divider span { color: #999; font-size: 14px; }
        input { width: 100%; padding: 15px; font-size: 16px; border-radius: 10px; border: 2px solid #ddd; margin-bottom: 15px; transition: border 0.3s; }
        input:focus { outline: none; border-color: #667eea; }
        button[type="submit"] { width: 100%; padding: 15px; font-size: 16px; border-radius: 10px; border: none; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; cursor: pointer; font-weight: bold; margin-top: 10px; transition: transform 0.2s; }
        button[type="submit"]:hover { transform: translateY(-2px); }
        .link { color: #667eea; text-decoration: none; font-size: 14px; display: block; text-align: center; margin-top: 20px; }
        .link:hover { text-decoration: underline; }
        .phone-input-group { display: flex; gap: 10px; align-items: center; }
        .phone-input-group select { padding: 15px; font-size: 16px; border-radius: 10px; border: 2px solid #ddd; background: white; }
        .phone-input-group input { flex: 1; margin-bottom: 0; }
        @media (max-width: 480px) { .container { padding: 25px; } }
    </style>
</head>
<body>
    <div class="container">
        <h1>BRICK AI <span class="emoji">👾</span></h1>
        <p class="subtitle">Sign in to continue</p>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        <div class="login-options">
            <button onclick="location.href='/auth/google'" class="social-btn google-btn">🔴 Google</button>
            <button onclick="location.href='/auth/facebook'" class="social-btn facebook-btn">🔵 Facebook</button>
            <button onclick="location.href='/register'" class="social-btn email-btn">📧 Create Account</button>
            <button onclick="document.getElementById('phoneForm').style.display='block'; this.style.display='none';" class="social-btn phone-btn">📱 Phone Number</button>
        </div>
        <div id="phoneForm" style="display: none;">
            <form method="post" action="/auth/phone">
                <div class="phone-input-group">
                    <select name="country_code">
                        <option value="+254">🇰🇪 +254</option>
                        <option value="+1">🇺🇸 +1</option>
                        <option value="+44">🇬🇧 +44</option>
                        <option value="+91">🇮🇳 +91</option>
                        <option value="+61">🇦🇺 +61</option>
                        <option value="+81">🇯🇵 +81</option>
                        <option value="+86">🇨🇳 +86</option>
                        <option value="+55">🇧🇷 +55</option>
                        <option value="+27">🇿🇦 +27</option>
                        <option value="+234">🇳🇬 +234</option>
                    </select>
                    <input type="tel" name="phone" placeholder="Phone Number" required>
                </div>
                <button type="submit">Send Code</button>
                <a href="#" onclick="document.getElementById('phoneForm').style.display='none'; document.querySelector('.phone-btn').style.display='flex'; return false;" class="link">Cancel</a>
            </form>
        </div>
        <div class="divider"><span>or</span></div>
        <form method="post" action="/login">
            <input type="email" name="email" placeholder="Email Address" required>
            <input type="password" name="password" placeholder="Password" required>
            <button type="submit">Login</button>
        </form>
        <a href="/register" class="link">Don't have an account? Sign Up</a>
        <a href="/forgot-password" class="link" style="font-size: 12px; margin-top: 8px;">Forgot Password?</a>
    </div>
</body>
</html>
"""

REGISTER_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Sign Up - BRICK AI 👾</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px; }
        .container { background: white; padding: 40px; border-radius: 20px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); width: 100%; max-width: 420px; }
        h1 { color: #333; text-align: center; margin-bottom: 10px; font-size: 2em; }
        .emoji { color: #ff0000; }
        .subtitle { text-align: center; color: #666; margin-bottom: 25px; }
        .error { background: #fee; color: #c33; padding: 12px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #c33; }
        .success { background: #efe; color: #3c3; padding: 12px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #3c3; }
        input { width: 100%; padding: 15px; font-size: 16px; border-radius: 10px; border: 2px solid #ddd; margin-bottom: 15px; transition: border 0.3s; }
        input:focus { outline: none; border-color: #667eea; }
        button[type="submit"] { width: 100%; padding: 15px; font-size: 16px; border-radius: 10px; border: none; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; cursor: pointer; font-weight: bold; margin-top: 10px; transition: transform 0.2s; }
        button[type="submit"]:hover { transform: translateY(-2px); }
        .link { color: #667eea; text-decoration: none; font-size: 14px; display: block; text-align: center; margin-top: 20px; }
        .link:hover { text-decoration: underline; }
        .phone-input-group { display: flex; gap: 10px; align-items: center; }
        .phone-input-group select { padding: 15px; font-size: 16px; border-radius: 10px; border: 2px solid #ddd; background: white; }
        .phone-input-group input { flex: 1; margin-bottom: 0; }
        .divider { display: flex; align-items: center; text-align: center; margin: 20px 0; }
        .divider::before, .divider::after { content: ''; flex: 1; border-bottom: 1px solid #ddd; }
        .divider::before { margin-right: 10px; }
        .divider::after { margin-left: 10px; }
        .divider span { color: #999; font-size: 14px; }
        .social-register { display: flex; gap: 10px; margin-top: 20px; }
        .social-register-btn { flex: 1; padding: 12px; border-radius: 10px; border: none; color: white; cursor: pointer; font-weight: bold; font-size: 14px; transition: transform 0.2s; display: flex; align-items: center; justify-content: center; gap: 8px; }
        .social-register-btn:hover { transform: translateY(-2px); }
        .google-register { background: #db4437; }
        .facebook-register { background: #1877f2; }
        @media (max-width: 480px) { .container { padding: 25px; } .social-register { flex-direction: column; } }
    </style>
</head>
<body>
    <div class="container">
        <h1>Create Account <span class="emoji">👾</span></h1>
        <p class="subtitle">Join BRICK AI today</p>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        <h3 style="margin-bottom: 15px; color: #333;">📧 Email Registration</h3>
        <form method="post" action="/register">
            <input type="text" name="username" placeholder="Username (3-20 chars)" required pattern="[a-zA-Z0-9_]{3,20}">
            <input type="email" name="email" placeholder="Email Address" required>
            <input type="password" name="password" placeholder="Password (min 8 chars)" required minlength="8">
            <input type="password" name="confirm_password" placeholder="Confirm Password" required>
            <button type="submit">Create Account</button>
        </form>
        
        <div class="divider"><span>or</span></div>
        
        <h3 style="margin-bottom: 15px; color: #333;">📱 Phone Registration</h3>
        <form method="post" action="/register/phone">
            <input type="text" name="username" placeholder="Username (3-20 chars)" required pattern="[a-zA-Z0-9_]{3,20}">
            <div class="phone-input-group">
                <select name="country_code">
                    <option value="+254">🇰🇪 +254</option>
                    <option value="+1">🇺🇸 +1</option>
                    <option value="+44">🇬🇧 +44</option>
                    <option value="+91">🇮🇳 +91</option>
                    <option value="+61">🇦🇺 +61</option>
                    <option value="+81">🇯🇵 +81</option>
                    <option value="+86">🇨🇳 +86</option>
                    <option value="+55">🇧🇷 +55</option>
                    <option value="+27">🇿🇦 +27</option>
                    <option value="+234">🇳🇬 +234</option>
                </select>
                <input type="tel" name="phone" placeholder="Phone Number" required>
            </div>
            <input type="password" name="password" placeholder="Password (min 8 chars)" required minlength="8">
            <input type="password" name="confirm_password" placeholder="Confirm Password" required>
            <button type="submit">Create Account with Phone</button>
        </form>
        
        <div class="divider"><span>or continue with</span></div>
        
        <div class="social-register">
            <button onclick="location.href='/auth/google'" class="social-register-btn google-register">🔴 Google</button>
            <button onclick="location.href='/auth/facebook'" class="social-register-btn facebook-register">🔵 Facebook</button>
        </div>
        
        <a href="/login" class="link">Already have an account? Login</a>
    </div>
</body>
</html>
"""

MAIN_APP_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>BRICK AI 👾</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f5f5f5; padding: 20px; min-height: 100vh; }
        .header { background: white; padding: 20px; border-radius: 15px; text-align: center; margin-bottom: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { color: #333; font-size: 2em; }
        .red-emoji { color: #ff0000; font-size: 1.2em; }
        .welcome { color: #666; margin-top: 5px; }
        .logout-btn { display: inline-block; margin-top: 10px; padding: 8px 20px; background: #ff4444; color: white; text-decoration: none; border-radius: 20px; font-size: 14px; }
        .search-box { width: 100%; padding: 18px; font-size: 18px; border-radius: 15px; border: 2px solid #ddd; margin-bottom: 20px; background: white; }
        .search-box:focus { outline: none; border-color: #667eea; }
        .buttons-container { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 15px; }
        .btn { padding: 18px; font-size: 16px; border-radius: 12px; border: none; color: white; cursor: pointer; font-weight: bold; transition: transform 0.2s; }
        .btn:hover { transform: translateY(-2px); }
        .wiki { background: linear-gradient(135deg, #11998e, #38ef7d); }
        .smart { background: linear-gradient(135deg, #667eea, #764ba2); }
        .ai-btn { background: linear-gradient(135deg, #f093fb, #f5576c); }
        .chat-btn { width: 100%; padding: 18px; font-size: 18px; border-radius: 12px; border: none; background: linear-gradient(135deg, #4facfe, #00f2fe); color: white; cursor: pointer; font-weight: bold; margin-top: 10px; }
        .result { background: white; margin: 20px 0; padding: 25px; border-radius: 15px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); color: #333; line-height: 1.6; }
        .result .ai-source { font-size: 12px; color: #999; margin-top: 10px; padding-top: 10px; border-top: 1px solid #eee; }
        .result .error-text { color: #c33; background: #fee; padding: 10px; border-radius: 8px; border-left: 4px solid #c33; }
        .result .success-text { color: #3c3; background: #efe; padding: 10px; border-radius: 8px; border-left: 4px solid #3c3; }
        .history-container { background: white; margin: 20px 0; padding: 20px; border-radius: 15px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .history-container h3 { color: #333; border-bottom: 2px solid #667eea; padding-bottom: 10px; margin-bottom: 15px; }
        .history-item { display: flex; justify-content: space-between; align-items: center; padding: 12px; background: #f9f9f9; margin-bottom: 8px; border-radius: 8px; border-left: 3px solid #667eea; }
        .history-item span { color: #333; font-size: 14px; }
        .history-item .mode { color: #666; font-size: 12px; margin-left: 10px; padding: 3px 8px; background: #eee; border-radius: 10px; }
        .clear-btn { background: #ff4444; color: white; border: none; padding: 8px 15px; border-radius: 5px; cursor: pointer; font-size: 12px; text-decoration: none; }
        .status-badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; margin-left: 10px; }
        .status-online { background: #4caf50; color: white; }
        .status-offline { background: #f44336; color: white; }
        .status-warning { background: #ff9800; color: white; }
        .provider-badge { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 11px; margin-left: 10px; }
        .provider-google { background: #db4437; color: white; }
        .provider-facebook { background: #1877f2; color: white; }
        .provider-phone { background: #25D366; color: white; }
        .provider-local { background: #667eea; color: white; }
        .api-status { font-size: 12px; margin-top: 5px; color: #666; }
        @media (max-width: 768px) { .buttons-container { grid-template-columns: 1fr; } }
    </style>
</head>
<body>
    <div class="header">
        <h1>BRICK AI <span class="red-emoji">👾</span></h1>
        <p class="welcome">
            Welcome, {{ session['username'] }}! 
            <span class="provider-badge provider-{{ session.get('auth_provider', 'local') }}">
                {{ session.get('auth_provider', 'local').upper() }}
            </span>
            <a href="/logout" class="logout-btn">Logout</a>
        </p>
        <div class="api-status">
            {% if gemini_available %}<span class="status-badge status-online">✅ Gemini</span>{% else %}<span class="status-badge status-offline">❌ Gemini</span>{% endif %}
            {% if huggingface_available %}<span class="status-badge status-online">✅ HuggingFace</span>{% else %}<span class="status-badge status-offline">❌ HuggingFace</span>{% endif %}
            {% if not gemini_available and not huggingface_available %}<span class="status-badge status-warning">⚠️ Using Simple Bot</span>{% endif %}
        </div>
    </div>
    <form method="post">
        <input type="text" name="query" class="search-box" placeholder="Ask anything..." value="{{ query or '' }}" required>
        <div class="buttons-container">
            <button type="submit" name="mode" value="wiki" class="btn wiki">🔎 WIKI</button>
            <button type="submit" name="mode" value="smart" class="btn smart">🌐 SMART</button>
            <button type="submit" name="mode" value="ai" class="btn ai-btn">✨ AI BOT</button>
        </div>
        <a href="/chat"><button type="button" class="chat-btn">💬 OPEN CHAT</button></a>
    </form>
    {% if result %}<div class="result">{{ result | safe }}</div>{% endif %}
    <div class="history-container">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <h3>🕒 Search History</h3>
            {% if history %}<a href="/clear_history" class="clear-btn">Clear</a>{% endif %}
        </div>
        {% if history %}
            {% for item in history %}
            <div class="history-item">
                <div>
                    <span style="color:#333; font-weight:bold;">{{ item.search_query }}</span>
                    <span class="mode">{{ item.mode | upper }}</span>
                </div>
                <span style="color:#999; font-size:12px;">{{ item.timestamp.strftime('%H:%M') }}</span>
            </div>
            {% endfor %}
        {% else %}
            <p style="color:#999; text-align:center;">No searches yet. Try searching something!</p>
        {% endif %}
    </div>
</body>
</html>
"""

CHAT_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Chat - BRICK AI 👾</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f5f5f5; height: 100vh; display: flex; flex-direction: column; }
        .chat-header { background: white; padding: 20px; text-align: center; border-bottom: 2px solid #667eea; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .chat-header h1 { color: #333; font-size: 1.5em; }
        .back-link { display: inline-block; margin-top: 10px; color: #667eea; text-decoration: none; }
        .chat-container { flex: 1; overflow-y: auto; padding: 20px; background: #f5f5f5; }
        .message { margin-bottom: 20px; display: flex; flex-direction: column; }
        .message.user { align-items: flex-end; }
        .message.bot { align-items: flex-start; }
        .message-content { max-width: 80%; padding: 15px 20px; border-radius: 15px; word-wrap: break-word; }
        .message.user .message-content { background: linear-gradient(135deg, #667eea, #764ba2); color: white; border-bottom-right-radius: 5px; }
        .message.bot .message-content { background: white; color: #333; border-bottom-left-radius: 5px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .message.bot .message-source { font-size: 10px; color: #999; margin-top: 4px; padding-left: 5px; }
        .input-container { background: white; padding: 20px; border-top: 2px solid #ddd; display: flex; gap: 10px; }
        .chat-input { flex: 1; padding: 15px; border: 2px solid #ddd; border-radius: 25px; font-size: 16px; resize: none; }
        .chat-input:focus { outline: none; border-color: #667eea; }
        .send-btn { padding: 15px 30px; background: linear-gradient(135deg, #667eea, #764ba2); color: white; border: none; border-radius: 25px; cursor: pointer; font-weight: bold; }
        .bot-selector { background: white; padding: 15px; text-align: center; border-bottom: 1px solid #ddd; }
        .bot-selector select { padding: 10px 20px; border-radius: 10px; border: 2px solid #ddd; font-size: 16px; }
    </style>
</head>
<body>
    <div class="chat-header">
        <h1>BRICK AI Chat 👾</h1>
        <a href="/" class="back-link">← Back to Home</a>
    </div>
    <div class="bot-selector">
        <select id="botSelect">
            <option value="gemini">✨ Gemini AI</option>
            <option value="huggingface">🤗 HuggingFace AI</option>
            <option value="simple">💡 Simple Bot</option>
        </select>
    </div>
    <div class="chat-container" id="chatContainer">
        <div class="message bot">
            <div class="message-content">Hello! I'm BRICK AI. How can I help you today?</div>
            <div class="message-source">🤖 AI Assistant</div>
        </div>
    </div>
    <div class="input-container">
        <textarea class="chat-input" id="messageInput" placeholder="Type your message..." rows="1"></textarea>
        <button class="send-btn" onclick="sendMessage()">Send</button>
    </div>
    <script>
        const chatContainer = document.getElementById('chatContainer');
        const messageInput = document.getElementById('messageInput');
        function sendMessage() {
            const message = messageInput.value.trim();
            if (!message) return;
            addMessage(message, 'user');
            messageInput.value = '';
            const botType = document.getElementById('botSelect').value;
            fetch('/chat_api', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message: message, bot: botType})
            })
            .then(response => response.json())
            .then(data => { addMessage(data.response, 'bot', data.source || '🤖'); })
            .catch(error => { addMessage('Sorry, I encountered an error. Please try again.', 'bot', '❌ Error'); console.error('Chat error:', error); });
        }
        function addMessage(text, sender, source) {
            const messageDiv = document.createElement('div');
            messageDiv.className = 'message ' + sender;
            const contentDiv = document.createElement('div');
            contentDiv.className = 'message-content';
            contentDiv.textContent = text;
            messageDiv.appendChild(contentDiv);
            if (sender === 'bot' && source) {
                const sourceDiv = document.createElement('div');
                sourceDiv.className = 'message-source';
                sourceDiv.textContent = source;
                messageDiv.appendChild(sourceDiv);
            }
            chatContainer.appendChild(messageDiv);
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
        messageInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
        });
    </script>
</body>
</html>
"""

# Routes
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not validate_username(username):
            flash('Username must be 3-20 characters (letters, numbers, underscore)', 'error')
            return redirect(url_for('register'))
        
        if not validate_email(email):
            flash('Please enter a valid email address', 'error')
            return redirect(url_for('register'))
        
        if len(password) < 8:
            flash('Password must be at least 8 characters long', 'error')
            return redirect(url_for('register'))
        
        if password != confirm_password:
            flash('Passwords do not match!', 'error')
            return redirect(url_for('register'))
        
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash('Username or email already taken!', 'error')
            return redirect(url_for('register'))
        
        new_user = User(
            username=username, 
            email=email,
            password_hash=generate_password_hash(password),
            auth_provider='local',
            is_verified=True
        )
        db.session.add(new_user)
        db.session.commit()
        flash('Account created successfully! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template_string(REGISTER_TEMPLATE)

@app.route('/register/phone', methods=['POST'])
def register_phone():
    username = request.form.get('username')
    country_code = request.form.get('country_code')
    phone = request.form.get('phone')
    password = request.form.get('password')
    confirm_password = request.form.get('confirm_password')
    full_phone = country_code + phone
    
    if not validate_username(username):
        flash('Username must be 3-20 characters (letters, numbers, underscore)', 'error')
        return redirect(url_for('register'))
    
    if not validate_phone(full_phone):
        flash('Please enter a valid phone number', 'error')
        return redirect(url_for('register'))
    
    if len(password) < 8:
        flash('Password must be at least 8 characters long', 'error')
        return redirect(url_for('register'))
    
    if password != confirm_password:
        flash('Passwords do not match!', 'error')
        return redirect(url_for('register'))
    
    existing_user = User.query.filter((User.username == username) | (User.phone == full_phone)).first()
    if existing_user:
        flash('Username or phone number already registered!', 'error')
        return redirect(url_for('register'))
    
    new_user = User(
        username=username,
        phone=full_phone,
        password_hash=generate_password_hash(password),
        auth_provider='phone',
        is_verified=True
    )
    db.session.add(new_user)
    db.session.commit()
    flash('Account created successfully! Please login.', 'success')
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email, auth_provider='local').first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['auth_provider'] = user.auth_provider
            flash('Logged in successfully!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid email or password!', 'error')
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/auth/google')
def auth_google():
    email = 'demo.google@gmail.com'
    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(
            username='Google_User',
            email=email,
            auth_provider='google',
            provider_id='google_12345',
            is_verified=True
        )
        db.session.add(user)
        db.session.commit()
        flash('Google account linked successfully!', 'success')
    else:
        flash('Logged in with Google successfully!', 'success')
    
    session['user_id'] = user.id
    session['username'] = user.username
    session['auth_provider'] = 'google'
    return redirect(url_for('home'))

@app.route('/auth/facebook')
def auth_facebook():
    email = 'demo.facebook@gmail.com'
    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(
            username='Facebook_User',
            email=email,
            auth_provider='facebook',
            provider_id='fb_12345',
            is_verified=True
        )
        db.session.add(user)
        db.session.commit()
        flash('Facebook account linked successfully!', 'success')
    else:
        flash('Logged in with Facebook successfully!', 'success')
    
    session['user_id'] = user.id
    session['username'] = user.username
    session['auth_provider'] = 'facebook'
    return redirect(url_for('home'))

@app.route('/auth/phone', methods=['POST'])
def auth_phone():
    country_code = request.form.get('country_code')
    phone = request.form.get('phone')
    full_phone = country_code + phone
    
    user = User.query.filter_by(phone=full_phone).first()
    if not user:
        user = User(
            username=f'User_{phone[-4:]}',
            phone=full_phone,
            auth_provider='phone',
            provider_id=full_phone,
            is_verified=True
        )
        db.session.add(user)
        db.session.commit()
        flash('Phone number registered successfully!', 'success')
    else:
        flash('Logged in with phone number!', 'success')
    
    session['user_id'] = user.id
    session['username'] = user.username
    session['auth_provider'] = 'phone'
    return redirect(url_for('home'))

@app.route('/forgot-password')
def forgot_password():
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Forgot Password - BRICK AI</title></head>
    <body style="font-family: Arial; display: flex; justify-content: center; align-items: center; height: 100vh; background: #f5f5f5; margin: 0;">
        <div style="background: white; padding: 40px; border-radius: 20px; max-width: 400px; width: 100%; text-align: center; box-shadow: 0 20px 60px rgba(0,0,0,0.2);">
            <h2 style="color: #333;">🔑 Reset Password</h2>
            <p style="color: #666; margin: 15px 0;">Enter your email to receive a password reset link.</p>
            <input type="email" placeholder="Email Address" style="width: 100%; padding: 15px; border-radius: 10px; border: 2px solid #ddd; margin: 15px 0; font-size: 16px; box-sizing: border-box;">
            <button style="width: 100%; padding: 15px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 10px; font-weight: bold; font-size: 16px; cursor: pointer; transition: transform 0.2s;">Send Reset Link</button>
            <a href="/login" style="display: block; margin-top: 20px; color: #667eea; text-decoration: none;">← Back to Login</a>
        </div>
    </body>
    </html>
    """

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/clear_history')
def clear_history():
    if 'user_id' in session:
        SearchHistory.query.filter_by(user_id=session['user_id']).delete()
        db.session.commit()
    return redirect(url_for('home'))

@app.route('/chat')
def chat():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template_string(CHAT_TEMPLATE)

@app.route('/chat_api', methods=['POST'])
def chat_api():
    if 'user_id' not in session:
        return jsonify({'response': 'Please login first', 'source': '❌ Error'})
    try:
        data = request.get_json()
        message = data.get('message', '')
        bot_type = data.get('bot', 'gemini')
        if not message:
            return jsonify({'response': 'Please enter a message', 'source': '❌ Error'})
        
        if bot_type == 'gemini':
            response, error = get_gemini_response(message)
            if response: 
                source = "✨ Gemini AI"
            else:
                response, error2 = get_huggingface_response(message)
                if response: 
                    source = "🤗 HuggingFace AI (Fallback)"
                else:
                    response = enhanced_simple_bot(message)
                    source = "💡 Simple Bot"
        elif bot_type == 'huggingface':
            response, error = get_huggingface_response(message)
            if response: 
                source = "🤗 HuggingFace AI"
            else:
                response, error2 = get_gemini_response(message)
                if response: 
                    source = "✨ Gemini AI (Fallback)"
                else:
                    response = enhanced_simple_bot(message)
                    source = "💡 Simple Bot"
        else:
            response = enhanced_simple_bot(message)
            source = "💡 Simple Bot"
        
        chat_msg = ChatMessage(user_id=session['user_id'], message=message, response=response, chatbot=bot_type)
        db.session.add(chat_msg)
        db.session.commit()
        return jsonify({'response': response, 'source': source})
    except Exception as e:
        error_msg = str(e)
        print(f"Chat API error: {error_msg}")
        return jsonify({'response': f'Error: {error_msg}', 'source': '❌ Error'})

@app.route("/", methods=["GET", "POST"])
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    result = ""
    query = ""
    gemini_available = gemini_client is not None
    huggingface_available = HUGGINGFACE_API_KEY and HUGGINGFACE_API_KEY != ""
    
    if request.method == "POST":
        query = request.form.get("query", "").strip()
        mode = request.form.get("mode")
        
        if query:
            try:
                if mode == "wiki":
                    # Use the improved Wikipedia search
                    summary, error = search_wikipedia(query)
                    if summary:
                        result = f"<h3>📚 Wikipedia: {escape(query)}</h3><p>{escape(summary)}</p>"
                    else:
                        result = f"""
                        <h3>📚 Wikipedia</h3>
                        <div class="error-text">
                            <strong>Error:</strong> {escape(error)}
                            <br><br>
                            <strong>Tip:</strong> Try using SMART search or AI BOT instead.
                        </div>
                        """
                    
                elif mode == "smart":
                    # Try Wikipedia with better error handling
                    try:
                        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(query)}"
                        headers = {'User-Agent': 'BRICK-AI/1.0'}
                        response = requests.get(url, headers=headers, timeout=10)
                        
                        if response.status_code == 200:
                            try:
                                data = response.json()
                                if data and 'extract' in data and data['extract']:
                                    result = f"<h3>🌐 Smart Search: {escape(query)}</h3><p>{escape(data['extract'])}</p>"
                                else:
                                    result = f"""
                                    <h3>🌐 Smart Search: {escape(query)}</h3>
                                    <div class="error-text">No information found. Try WIKI or AI BOT.</div>
                                    """
                            except json.JSONDecodeError:
                                result = f"""
                                <h3>🌐 Smart Search: {escape(query)}</h3>
                                <div class="error-text">Error parsing response. Try WIKI or AI BOT.</div>
                                """
                        else:
                            # Fallback to regular Wikipedia
                            summary, error = search_wikipedia(query)
                            if summary:
                                result = f"<h3>🌐 Smart Search: {escape(query)}</h3><p>{escape(summary)}</p>"
                            else:
                                result = f"""
                                <h3>🌐 Smart Search: {escape(query)}</h3>
                                <div class="error-text">No results found. Try WIKI or AI BOT.</div>
                                """
                    except requests.exceptions.Timeout:
                        result = f"""
                        <h3>🌐 Smart Search: {escape(query)}</h3>
                        <div class="error-text">Request timed out. Please try again.</div>
                        """
                    except Exception as e:
                        result = f"""
                        <h3>🌐 Smart Search: {escape(query)}</h3>
                        <div class="error-text">Error: {escape(str(e))}. Try WIKI or AI BOT.</div>
                        """
                        
                elif mode == "ai":
                    ai_answer, source, error = get_ai_response(query, prefer_gemini=True)
                    if ai_answer:
                        formatted_answer = escape(ai_answer).replace('\n', '<br>')
                        source_emoji = {'gemini': '✨', 'huggingface': '🤗', 'simple': '💡'}.get(source, '🤖')
                        result = f"""
                        <h3>✨ AI Answer: {escape(query)}</h3>
                        <p>{formatted_answer}</p>
                        <div class="ai-source">{source_emoji} Powered by {source.title()} AI</div>
                        """
                    else:
                        error_msg = error or "Unknown error occurred"
                        result = f"""
                        <h3>❌ AI Error</h3>
                        <div class="error-text">
                            <strong>Error:</strong> {escape(error_msg)}
                            <br><br>
                            <strong>Tip:</strong> Using Simple Bot as fallback:
                            <br><br>
                            {escape(enhanced_simple_bot(query))}
                        </div>
                        """
            except Exception as e:
                error_msg = str(e)
                print(f"Home page error: {error_msg}")
                print(traceback.format_exc())
                result = f"""
                <h3>❌ Error</h3>
                <div class="error-text">
                    <strong>Error:</strong> {escape(error_msg)}
                    <br><br>
                    <strong>Tip:</strong> Try using a different search mode.
                </div>
                """
            
            try:
                new_search = SearchHistory(user_id=session['user_id'], search_query=query, mode=mode)
                db.session.add(new_search)
                db.session.commit()
            except Exception as e:
                print(f"Failed to save history: {e}")

    history = SearchHistory.query.filter_by(user_id=session['user_id']).order_by(SearchHistory.timestamp.desc()).limit(10).all()
    
    return render_template_string(
        MAIN_APP_TEMPLATE,
        result=result,
        query=query,
        history=history,
        gemini_available=gemini_available,
        huggingface_available=huggingface_available
    )

# Create database
with app.app_context():
    db.drop_all()
    db.create_all()
    print("✅ Database tables recreated successfully")

if __name__ == "__main__":
      port = int(os.environ.get("PORT", 8080))
      app.run(host="0.0.0.0", port=port) 
  if __name__ == "__main__":
      port = int(os.environ.get("PORT", 8080))
      app.run(host="0.0.0.0", port=port)
