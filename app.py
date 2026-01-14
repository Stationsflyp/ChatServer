from flask import Flask, jsonify, request, send_file
from flask_socketio import SocketIO, emit
from datetime import datetime
import os
from pathlib import Path
from dotenv import load_dotenv
import logging

# Configuración de logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'oxcy-secret-key')
# IMPORTANTE: permitimos todos los orígenes para el túnel
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

PORT = int(os.getenv('PORT', 8001))
TUNNEL_URL = os.getenv('CLOUDFLARE_TUNNEL_URL', 'https://compounds-collecting-hammer-subscriber.trycloudflare.com')

# --- RUTAS DEL UPDATER ---
@app.route('/')
def index():
    return jsonify({"status": "running", "server": "OxcyCombined", "mode": "Updater+Chat"})

@app.route('/health')
def health():
    return jsonify({"status": "ok", "port": PORT})

# --- LÓGICA DEL CHAT ---
users = {}

@socketio.on('connect')
def handle_connect():
    logger.info(f'NUEVA CONEXIÓN: {request.sid}')

@socketio.on('join_chat')
def handle_join(data):
    username = data.get('username', 'Anónimo').strip()
    users[request.sid] = username
    logger.info(f'USUARIO UNIDO: {username}')
    
    # Enviar respuesta de éxito al cliente
    emit('joined_response', {
        'username': username,
        'users_list': list(users.values()),
        'messages': [] # Puedes añadir historial aquí
    })
    
    # Notificar a otros
    socketio.emit('user_joined', {'user': username, 'users_list': list(users.values())}, broadcast=True)

@socketio.on('send_message')
def handle_message(data):
    username = users.get(request.sid, 'Anónimo')
    content = data.get('message', '')
    if content:
        msg = {'user': username, 'content': content, 'timestamp': datetime.utcnow().isoformat()}
        socketio.emit('new_message', msg, broadcast=True)
        logger.info(f'MENSAJE de {username}: {content}')

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in users:
        user = users.pop(request.sid)
        socketio.emit('user_left', {'user': user}, broadcast=True)
        logger.info(f'USUARIO DESCONECTADO: {user}')

if __name__ == '__main__':
    logger.info(f'Iniciando Servidor Combinado en puerto {PORT} con EVENTLET...')
    # USAR socketio.run en lugar de app.run
    socketio.run(app, host='0.0.0.0', port=PORT, debug=False)
