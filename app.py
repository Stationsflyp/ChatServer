import eventlet
eventlet.monkey_patch()

from flask import Flask, jsonify, request, send_file
from flask_socketio import SocketIO, emit
from datetime import datetime, timezone
import os
from pathlib import Path
from dotenv import load_dotenv
import logging

# Logs limpios
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'oxcy-secret-key')
app.config['JSON_SORT_KEYS'] = False

# Configuración ultra-compatible para túneles
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

# --- UPDATER LOGIC ---
RELEASES_DB = {
    '0.1.0': {
        'version': '0.1.0',
        'pub_date': datetime.now(timezone.utc).isoformat(),
        'notes': 'Initial release',
        'platforms': {'windows-x86_64': {'url': f'{TUNNEL_URL}/download/0.1.0/OxcyShop-Executor_0.1.0_x64_en-US.msi', 'sig': 'sig_0.1.0', 'with_elevated_task': False}}
    },
    '0.2.0': {
        'version': '0.2.0',
        'pub_date': datetime.now(timezone.utc).isoformat(),
        'notes': 'Improved memory protection and dump analysis',
        'platforms': {'windows-x86_64': {'url': f'{TUNNEL_URL}/download/0.2.0/OxcyShop-Executor_0.2.0_x64_en-US.msi', 'sig': 'sig_0.2.0', 'with_elevated_task': False}}
    }
}

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'server': 'OxcyCombined'})

@socketio.on('connect')
def handle_connect():
    logger.info(f'>>> CLIENTE INTENTANDO CONECTAR: {request.sid}')

@socketio.on('join_chat')
def handle_join(data):
    username = data.get('username', 'User').strip()
    logger.info(f'>>> LOGIN: {username}')
    emit('joined_response', {
        'username': username,
        'users_list': [username],
        'messages': []
    })

@app.route('/', methods=['GET'])
def index():
    logger.info(f"PETICIÓN WEB RECIBIDA DESDE: {request.remote_addr}")
    return jsonify({'name': 'OxcyShop Combined Server', 'status': 'online', 'chat': 'ready'})

if __name__ == '__main__':
    logger.info(f'--- SERVIDOR INICIADO EN PUERTO {PORT} ---')
    socketio.run(app, host='0.0.0.0', port=PORT, debug=False)
