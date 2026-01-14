import eventlet
eventlet.monkey_patch()  # ¡CRÍTICO: Debe ir antes de cualquier otro import!

from flask import Flask, jsonify, request, send_file
from flask_socketio import SocketIO, emit
from datetime import datetime
import os
from pathlib import Path
from dotenv import load_dotenv
import logging

# Configuración de logs detallada
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'oxcy-secret-key')
app.config['JSON_SORT_KEYS'] = False

# Activamos logs de SocketIO para ver los intentos de conexión en la terminal
socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    async_mode='eventlet',
    logger=True, 
    engineio_logger=True
)

PORT = int(os.getenv('PORT', 8001))
LATEST_VERSION = os.getenv('LATEST_VERSION', '0.2.0')
TUNNEL_URL = os.getenv('CLOUDFLARE_TUNNEL_URL', 'https://compounds-collecting-hammer-subscriber.trycloudflare.com')

RELEASES_DIR = Path('releases')
RELEASES_DIR.mkdir(exist_ok=True)

# --- UPDATER LOGIC ---
RELEASES_DB = {
    '0.1.0': {
        'version': '0.1.0',
        'pub_date': '2024-01-01T00:00:00Z',
        'notes': 'Initial release',
        'platforms': {'windows-x86_64': {'url': f'{TUNNEL_URL}/download/0.1.0/OxcyShop-Executor_0.1.0_x64_en-US.msi', 'sig': 'sig_0.1.0', 'with_elevated_task': False}}
    },
    '0.2.0': {
        'version': '0.2.0',
        'pub_date': datetime.utcnow().isoformat() + 'Z',
        'notes': 'Improved memory protection and dump analysis',
        'platforms': {'windows-x86_64': {'url': f'{TUNNEL_URL}/download/0.2.0/OxcyShop-Executor_0.2.0_x64_en-US.msi', 'sig': 'sig_0.2.0', 'with_elevated_task': False}}
    }
}

@app.route('/updates', methods=['GET', 'POST'])
def check_updates():
    current_version = request.args.get('version', '0.1.0')
    target = request.args.get('target', 'windows-x86_64')
    if current_version >= LATEST_VERSION:
        return jsonify({})
    release = RELEASES_DB.get(LATEST_VERSION)
    if not release:
        return jsonify({})
    platform = release.get('platforms', {}).get(target)
    if not platform:
        return jsonify({})
    return jsonify({'version': release['version'], 'pub_date': release['pub_date'], 'url': platform['url'], 'signature': platform['sig'], 'notes': release.get('notes', ''), 'with_elevated_task': platform.get('with_elevated_task', False)})

@app.route('/download/<path:filepath>', methods=['GET'])
def download_release(filepath):
    file_path = RELEASES_DIR / filepath
    if not file_path.exists():
        return jsonify({'error': 'File not found'}), 404
    return send_file(file_path, as_attachment=True)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'latest_version': LATEST_VERSION, 'timestamp': datetime.utcnow().isoformat(), 'tunnel_url': TUNNEL_URL})

# --- CHAT LOGIC ---
users = {}
messages_history = []
MAX_HISTORY = 100

def serialize_message(user, content, timestamp=None):
    if timestamp is None:
        timestamp = datetime.utcnow().isoformat()
    return {'user': user, 'content': content, 'timestamp': timestamp}

@socketio.on('connect')
def handle_connect():
    logger.info(f'NUEVA CONEXIÓN SOCKET: {request.sid}')

@socketio.on('join_chat')
def handle_join(data):
    username = data.get('username', f'User_{request.sid[:8]}').strip()
    if not username or len(username) > 20:
        emit('error', {'message': 'Invalid username'})
        return
    users[request.sid] = username
    message = serialize_message('System', f'{username} joined the chat')
    messages_history.append(message)
    socketio.emit('user_joined', {'user': username, 'users_list': list(users.values())}, broadcast=True)
    emit('joined_response', {'username': username, 'users_list': list(users.values()), 'messages': messages_history[-30:]})

@socketio.on('send_message')
def handle_message(data):
    if request.sid not in users:
        return
    username = users[request.sid]
    content = data.get('message', '').strip()
    if not content: return
    message = serialize_message(username, content)
    messages_history.append(message)
    if len(messages_history) > MAX_HISTORY: messages_history.pop(0)
    socketio.emit('new_message', message, broadcast=True)

@socketio.on('typing')
def handle_typing(data):
    if request.sid in users:
        socketio.emit('user_typing', {'user': users[request.sid], 'is_typing': data.get('is_typing', False)}, broadcast=True, include_self=False)

@app.route('/', methods=['GET'])
def index():
    return jsonify({'name': 'OxcyShop Combined Server', 'mode': 'Updater + Chat', 'status': 'running'})

if __name__ == '__main__':
    logger.info(f'Starting Combined Server on 0.0.0.0:{PORT} with EVENTLET...')
    socketio.run(app, host='0.0.0.0', port=PORT, debug=False)
