import eventlet
eventlet.monkey_patch()

from flask import Flask, jsonify, request, send_file
from flask_socketio import SocketIO, emit
from datetime import datetime, timezone
import os
from pathlib import Path
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'oxcy-secret-key')
app.config['JSON_SORT_KEYS'] = False

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    async_mode='eventlet',
    engineio_logger=True, 
    logger=True,
    always_connect=True
)

PORT = int(os.getenv('PORT', 8001))
LATEST_VERSION = os.getenv('LATEST_VERSION', '0.2.0')
TUNNEL_URL = os.getenv('CLOUDFLARE_TUNNEL_URL', 'https://compounds-collecting-hammer-subscriber.trycloudflare.com')

RELEASES_DIR = Path('releases')
RELEASES_DIR.mkdir(exist_ok=True)

# --- CHAT STATE ---
users = {}
messages_history = []
MAX_HISTORY = 50

def serialize_message(user, content):
    return {
        'user': user, 
        'content': content, 
        'timestamp': datetime.now(timezone.utc).isoformat()
    }

# --- UPDATER ROUTES ---
@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'server': 'OxcyCombined'})

@app.route('/')
def index():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>OxcyShop | Network</title>
        <style>
            :root {
                --primary: #8b5cf6;
                --bg: #0a0a0c;
            }
            body { 
                background: var(--bg); 
                color: #fff; 
                font-family: 'Inter', system-ui, -apple-system, sans-serif; 
                display: flex; 
                align-items: center; 
                justify-content: center; 
                height: 100vh; 
                margin: 0;
                overflow: hidden;
            }
            .bg-beams {
                position: fixed;
                inset: 0;
                background: 
                    radial-gradient(circle at 20% 30%, rgba(139, 92, 246, 0.08) 0%, transparent 50%),
                    radial-gradient(circle at 80% 70%, rgba(139, 92, 246, 0.04) 0%, transparent 50%);
                z-index: -1;
            }
            .container {
                text-align: center;
                padding: 4rem 5rem;
                border-radius: 2.5rem;
                background: rgba(18, 18, 20, 0.4);
                backdrop-filter: blur(40px);
                box-shadow: 0 40px 100px -20px rgba(0, 0, 0, 0.8);
                position: relative;
                border: 1px solid rgba(139, 92, 246, 0.15);
            }
            h1 { 
                font-size: 2.8rem; 
                font-weight: 900; 
                letter-spacing: -0.05em;
                margin: 0;
                background: linear-gradient(to bottom, #fff 40%, rgba(255,255,255,0.5));
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                text-transform: uppercase;
                font-style: italic;
                line-height: 1;
            }
            .brand-purple {
                color: var(--primary);
                -webkit-text-fill-color: var(--primary);
            }
            .subtitle { 
                color: rgba(255, 255, 255, 0.3); 
                font-size: 0.75rem; 
                font-weight: 800; 
                text-transform: uppercase; 
                letter-spacing: 0.5em; 
                margin-top: 1.2rem; 
            }
            .status-tag { 
                display: inline-flex; 
                align-items: center; 
                gap: 0.7rem; 
                margin-top: 3rem;
                background: rgba(139, 92, 246, 0.08);
                color: var(--primary);
                padding: 0.6rem 1.4rem;
                border-radius: 1rem;
                font-size: 0.65rem;
                font-weight: 900;
                border: 1px solid rgba(139, 92, 246, 0.2);
                letter-spacing: 0.25em;
            }
            .dot { 
                width: 6px; 
                height: 6px; 
                background: var(--primary); 
                border-radius: 50%; 
                box-shadow: 0 0 15px var(--primary); 
                animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; 
            }
            @keyframes pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.3; transform: scale(0.8); } }
        </style>
    </head>
    <body>
        <div class="bg-beams"></div>
        <div class="container">
            <h1>OxcyShop <span class="brand-purple">Chat</span></h1>
            <div class="subtitle">Executor Node • Restricted Access</div>
            <div class="status-tag">
                <div class="dot"></div>
                P2P BRIDGE ACTIVE
            </div>
        </div>
    </body>
    </html>
    """, 403

# --- CHAT EVENTS ---
@socketio.on('connect')
def handle_connect():
    logger.info(f'>>> SOCKET CONNECT: {request.sid}')

@socketio.on('join_chat')
def handle_join(data):
    username = data.get('username', 'User').strip()
    users[request.sid] = username
    
    # Broadcast to others
    msg = serialize_message('System', f'{username} joined')
    messages_history.append(msg)
    socketio.emit('user_joined', {'user': username, 'users_list': list(users.values()), 'message': msg})
    
    # Send response to joiner
    emit('joined_response', {
        'username': username,
        'users_list': list(users.values()),
        'messages': messages_history[-30:]
    })

@socketio.on('send_message')
def handle_message(data):
    if request.sid not in users: return
    username = users[request.sid]
    content = data.get('message', '').strip()
    if not content: return
    
    msg = serialize_message(username, content)
    messages_history.append(msg)
    if len(messages_history) > MAX_HISTORY: messages_history.pop(0)
    
    socketio.emit('new_message', msg)

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in users:
        user = users.pop(request.sid)
        msg = serialize_message('System', f'{user} left')
        messages_history.append(msg)
        socketio.emit('user_left', {'user': user, 'users_list': list(users.values())})

if __name__ == '__main__':
    logger.info(f'--- SERVIDOR INICIADO EN PUERTO {PORT} ---')
    socketio.run(app, host='0.0.0.0', port=PORT, debug=False)
