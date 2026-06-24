# BRICK AI 👾

An AI-powered search and chat assistant with web search capabilities.

## Features
- 🤖 AI Chat Assistant with Gemini API integration
- 🔍 Web and Wikipedia search
- 👤 User authentication
- 💬 Chat history
- ⚙️ Theme customization
- 📊 Activity tracking
- 🔒 Secure and rate-limited

## Technology Stack
- **Backend**: Flask (Python)
- **Database**: SQLite
- **AI**: Google Gemini API
- **Frontend**: HTML, CSS, JavaScript
- **Deployment**: Render.com

## Local Development

### Prerequisites
- Python 3.8+
- pip

### Installation
```bash
# Clone the repository
git clone https://github.com/yourusername/brick-ai.git
cd brick-ai

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your credentials

# Run the application
python app.py