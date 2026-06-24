from flask import Flask

app = Flask(__name__)

@app.route('/')
def hello():
    return 'Hello World! BRICK AI is running!'

@app.route('/test')
def test():
    return 'Test route is working!'

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)