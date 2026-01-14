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
    return jsonify({'name': 'OxcyShop Combined Server', 'status': 'online'})

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
    socketio.emit('user_joined', {'user': username, 'users_list': list(users.values()), 'message': msg}, broadcast=True)
    
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
    
    socketio.emit('new_message', msg, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in users:
        user = users.pop(request.sid)
        msg = serialize_message('System', f'{user} left')
        messages_history.append(msg)
        socketio.emit('user_left', {'user': user, 'users_list': list(users.values())}, broadcast=True)

if __name__ == '__main__':
    logger.info(f'--- SERVIDOR INICIADO EN PUERTO {PORT} ---')
    socketio.run(app, host='0.0.0.0', port=PORT, debug=False)
