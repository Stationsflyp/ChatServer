import eventlet
eventlet.monkey_patch()

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_socketio import SocketIO, emit
from datetime import datetime, timezone
import os
from pathlib import Path
from dotenv import load_dotenv
import logging
import uuid
import json
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'oxcy-secret-key')
app.config['JSON_SORT_KEYS'] = False
app.config['MAX_CONTENT_LENGTH'] = 12 * 1024 * 1024

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

UPLOADS_DIR = Path('uploads')
UPLOADS_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {'.dll', '.rar', '.zip', '.exe'}
MAX_FILE_SIZE = 12 * 1024 * 1024
MAX_FILES_PER_USER = 5

files_metadata_path = Path('uploads/metadata.json')

def load_files_metadata():
    if files_metadata_path.exists():
        try:
            with open(files_metadata_path, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_files_metadata(metadata):
    with open(files_metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)

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

# --- FILE UPLOAD ROUTES ---
@app.route('/api/files/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        filename = secure_filename(file.filename)
        ext = Path(filename).suffix.lower()
        
        if ext not in ALLOWED_EXTENSIONS:
            return jsonify({'error': f'File type not allowed. Allowed: {", ".join(ALLOWED_EXTENSIONS)}'}), 400
        
        if len(file.read()) > MAX_FILE_SIZE:
            file.seek(0)
            return jsonify({'error': 'File too large. Maximum size: 12 MB'}), 400
        
        file.seek(0)
        
        metadata = load_files_metadata()
        user_files = [f for f in metadata.values() if f.get('user_ip') == request.remote_addr]
        
        if len(user_files) >= MAX_FILES_PER_USER:
            return jsonify({'error': f'Maximum {MAX_FILES_PER_USER} files allowed per user'}), 403
        
        file_id = str(uuid.uuid4())[:8]
        
        file_path = UPLOADS_DIR / file_id / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        file.save(str(file_path))
        
        file_info = {
            'file_id': file_id,
            'original_name': filename,
            'current_name': filename,
            'size': os.path.getsize(str(file_path)),
            'uploaded_at': datetime.now(timezone.utc).isoformat(),
            'user_ip': request.remote_addr,
            'password_hash': None,
            'is_password_protected': False
        }
        
        metadata[file_id] = file_info
        save_files_metadata(metadata)
        
        download_link = f"{TUNNEL_URL}/api/files/download/{file_id}"
        
        logger.info(f'File uploaded: {file_id} by {request.remote_addr}')
        
        return jsonify({
            'success': True,
            'file_id': file_id,
            'download_link': download_link
        }), 201
    
    except Exception as e:
        logger.error(f'Upload error: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/files/<file_id>', methods=['DELETE'])
def delete_file(file_id):
    try:
        metadata = load_files_metadata()
        
        if file_id not in metadata:
            return jsonify({'error': 'File not found'}), 404
        
        file_info = metadata[file_id]
        if file_info.get('user_ip') != request.remote_addr:
            return jsonify({'error': 'Unauthorized'}), 403
        
        file_dir = UPLOADS_DIR / file_id
        if file_dir.exists():
            import shutil
            shutil.rmtree(file_dir)
        
        del metadata[file_id]
        save_files_metadata(metadata)
        
        logger.info(f'File deleted: {file_id}')
        
        return jsonify({'success': True}), 200
    
    except Exception as e:
        logger.error(f'Delete error: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/files/<file_id>/rename', methods=['PUT'])
def rename_file(file_id):
    try:
        data = request.get_json()
        new_name = data.get('new_name', '').strip()
        
        if not new_name:
            return jsonify({'error': 'New name is required'}), 400
        
        metadata = load_files_metadata()
        
        if file_id not in metadata:
            return jsonify({'error': 'File not found'}), 404
        
        file_info = metadata[file_id]
        if file_info.get('user_ip') != request.remote_addr:
            return jsonify({'error': 'Unauthorized'}), 403
        
        secure_new_name = secure_filename(new_name)
        file_dir = UPLOADS_DIR / file_id
        
        old_path = file_dir / file_info['current_name']
        new_path = file_dir / secure_new_name
        
        if old_path.exists():
            old_path.rename(new_path)
        
        file_info['current_name'] = secure_new_name
        metadata[file_id] = file_info
        save_files_metadata(metadata)
        
        logger.info(f'File renamed: {file_id}')
        
        return jsonify({'success': True, 'new_name': secure_new_name}), 200
    
    except Exception as e:
        logger.error(f'Rename error: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/files/<file_id>/password', methods=['PUT'])
def set_password(file_id):
    try:
        data = request.get_json()
        password = data.get('password', '').strip()
        
        if not password:
            return jsonify({'error': 'Password is required'}), 400
        
        metadata = load_files_metadata()
        
        if file_id not in metadata:
            return jsonify({'error': 'File not found'}), 404
        
        file_info = metadata[file_id]
        if file_info.get('user_ip') != request.remote_addr:
            return jsonify({'error': 'Unauthorized'}), 403
        
        file_info['password_hash'] = generate_password_hash(password)
        file_info['is_password_protected'] = True
        
        metadata[file_id] = file_info
        save_files_metadata(metadata)
        
        logger.info(f'Password set for file: {file_id}')
        
        return jsonify({'success': True}), 200
    
    except Exception as e:
        logger.error(f'Password error: {str(e)}')
        return jsonify({'error': str(e)}), 500

def get_password_page(file_id, file_name, error_message=None):
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>OxcyShop | Secure Download</title>
        <style>
            :root {{
                --primary: #8b5cf6;
                --bg: #0a0a0c;
            }}
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            body {{ 
                background: var(--bg); 
                color: #fff; 
                font-family: 'Inter', system-ui, -apple-system, sans-serif; 
                display: flex; 
                align-items: center; 
                justify-content: center; 
                min-height: 100vh; 
                padding: 20px;
            }}
            .bg-beams {{
                position: fixed;
                inset: 0;
                background: 
                    radial-gradient(circle at 20% 30%, rgba(139, 92, 246, 0.08) 0%, transparent 50%),
                    radial-gradient(circle at 80% 70%, rgba(139, 92, 246, 0.04) 0%, transparent 50%);
                z-index: -1;
            }}
            .container {{
                max-width: 420px;
                width: 100%;
                padding: 2.5rem;
                border-radius: 2rem;
                background: rgba(18, 18, 20, 0.4);
                backdrop-filter: blur(40px);
                box-shadow: 0 40px 100px -20px rgba(0, 0, 0, 0.8);
                border: 1px solid rgba(139, 92, 246, 0.15);
                position: relative;
            }}
            .icon {{
                width: 56px;
                height: 56px;
                background: rgba(139, 92, 246, 0.1);
                border: 1px solid rgba(139, 92, 246, 0.2);
                border-radius: 1rem;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto 1.5rem;
            }}
            .icon svg {{
                width: 28px;
                height: 28px;
                color: var(--primary);
            }}
            h1 {{ 
                font-size: 2rem; 
                font-weight: 900; 
                text-align: center;
                margin-bottom: 0.5rem;
                letter-spacing: -0.02em;
                text-transform: uppercase;
                font-style: italic;
            }}
            .subtitle {{
                text-align: center;
                color: rgba(255, 255, 255, 0.5);
                font-size: 0.875rem;
                margin-bottom: 2rem;
                font-weight: 600;
                letter-spacing: 0.05em;
            }}
            .file-info {{
                background: rgba(139, 92, 246, 0.05);
                border: 1px solid rgba(139, 92, 246, 0.15);
                border-radius: 0.75rem;
                padding: 1rem;
                margin-bottom: 1.5rem;
                text-align: center;
            }}
            .file-name {{
                font-size: 0.875rem;
                font-weight: 700;
                color: #fff;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                word-break: break-all;
            }}
            form {{
                display: flex;
                flex-direction: column;
                gap: 1rem;
            }}
            input[type="password"] {{
                width: 100%;
                padding: 0.75rem 1rem;
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 0.75rem;
                color: #fff;
                font-size: 0.875rem;
                font-family: inherit;
                transition: all 0.2s ease;
            }}
            input[type="password"]::placeholder {{
                color: rgba(255, 255, 255, 0.4);
            }}
            input[type="password"]:focus {{
                outline: none;
                border-color: var(--primary);
                background: rgba(139, 92, 246, 0.05);
            }}
            button {{
                width: 100%;
                padding: 0.75rem 1rem;
                background: var(--primary);
                color: #fff;
                border: none;
                border-radius: 0.75rem;
                font-size: 0.875rem;
                font-weight: 900;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                cursor: pointer;
                transition: all 0.2s ease;
                box-shadow: 0 4px 15px rgba(139, 92, 246, 0.3);
            }}
            button:hover {{
                background: rgba(139, 92, 246, 0.9);
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(139, 92, 246, 0.4);
            }}
            button:active {{
                transform: translateY(0);
            }}
            .error {{
                background: rgba(220, 38, 38, 0.1);
                border: 1px solid rgba(220, 38, 38, 0.3);
                color: #fca5a5;
                padding: 0.75rem 1rem;
                border-radius: 0.75rem;
                font-size: 0.875rem;
                font-weight: 600;
                display: flex;
                align-items: center;
                gap: 0.75rem;
                animation: shake 0.3s ease;
            }}
            .error svg {{
                width: 18px;
                height: 18px;
                flex-shrink: 0;
            }}
            @keyframes shake {{
                0%, 100% {{ transform: translateX(0); }}
                25% {{ transform: translateX(-5px); }}
                75% {{ transform: translateX(5px); }}
            }}
            .footer {{
                text-align: center;
                font-size: 0.75rem;
                color: rgba(255, 255, 255, 0.2);
                margin-top: 1.5rem;
                text-transform: uppercase;
                letter-spacing: 0.1em;
                font-weight: 600;
            }}
        </style>
    </head>
    <body>
        <div class="bg-beams"></div>
        <div class="container">
            <div class="icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                    <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
                </svg>
            </div>
            <h1>Secure <span style="color: var(--primary);">Download</span></h1>
            <p class="subtitle">Password Protected File</p>
            
            <div class="file-info">
                <div class="file-name">{file_name}</div>
            </div>

            {"<div class='error'><svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><circle cx='12' cy='12' r='10'></circle><line x1='12' y1='8' x2='12' y2='12'></line><line x1='12' y1='16' x2='12.01' y2='16'></line></svg>" + error_message + "</div>" if error_message else ""}

            <form method="POST" action="/api/files/download/{file_id}">
                <input 
                    type="password" 
                    name="password" 
                    placeholder="Enter password..." 
                    required 
                    autofocus
                    autocomplete="off"
                />
                <button type="submit">Unlock & Download</button>
            </form>

            <div class="footer">
                OxcyShop Security Protocol • Encrypted Transfer
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/api/files/download/<file_id>', methods=['GET'])
def download_file_get(file_id):
    try:
        metadata = load_files_metadata()
        
        if file_id not in metadata:
            return """
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Error - File Not Found</title>
                <style>
                    body { background: #0a0a0c; color: #fff; font-family: Inter, system-ui; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
                    .container { text-align: center; padding: 3rem; border-radius: 1.5rem; background: rgba(18, 18, 20, 0.4); backdrop-filter: blur(40px); border: 1px solid rgba(139, 92, 246, 0.15); }
                    h1 { color: #ff6b6b; margin: 0 0 1rem; }
                    p { color: rgba(255, 255, 255, 0.5); }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>❌ File Not Found</h1>
                    <p>This file may have been deleted or the link is invalid.</p>
                </div>
            </body>
            </html>
            """, 404
        
        file_info = metadata[file_id]
        
        if file_info.get('is_password_protected'):
            return get_password_page(file_id, file_info['current_name']), 403
        
        file_dir = UPLOADS_DIR / file_id
        file_path = file_dir / file_info['current_name']
        
        if not file_path.exists():
            return """
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Error - Server Error</title>
                <style>
                    body { background: #0a0a0c; color: #fff; font-family: Inter, system-ui; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
                    .container { text-align: center; padding: 3rem; border-radius: 1.5rem; background: rgba(18, 18, 20, 0.4); backdrop-filter: blur(40px); border: 1px solid rgba(139, 92, 246, 0.15); }
                    h1 { color: #ff6b6b; margin: 0 0 1rem; }
                    p { color: rgba(255, 255, 255, 0.5); }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>⚠️ Server Error</h1>
                    <p>The file could not be found on the server.</p>
                </div>
            </body>
            </html>
            """, 500
        
        logger.info(f'File downloaded (no password): {file_id}')
        
        return send_file(
            str(file_path),
            as_attachment=True,
            download_name=file_info['current_name']
        )
    
    except Exception as e:
        logger.error(f'Download error: {str(e)}')
        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Error - Server Error</title>
            <style>
                body {{ background: #0a0a0c; color: #fff; font-family: Inter, system-ui; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
                .container {{ text-align: center; padding: 3rem; border-radius: 1.5rem; background: rgba(18, 18, 20, 0.4); backdrop-filter: blur(40px); border: 1px solid rgba(139, 92, 246, 0.15); }}
                h1 {{ color: #ff6b6b; margin: 0 0 1rem; }}
                p {{ color: rgba(255, 255, 255, 0.5); }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>⚠️ Server Error</h1>
                <p>An error occurred: {str(e)}</p>
            </div>
        </body>
        </html>
        """, 500

@app.route('/api/files/download/<file_id>', methods=['POST'])
def download_file_post(file_id):
    try:
        metadata = load_files_metadata()
        
        if file_id not in metadata:
            return get_password_page(file_id, "Unknown", "File not found"), 404
        
        file_info = metadata[file_id]
        password = request.form.get('password', '').strip()
        
        if not password:
            return get_password_page(file_id, file_info['current_name'], "Password is required"), 400
        
        if not check_password_hash(file_info['password_hash'], password):
            return get_password_page(file_id, file_info['current_name'], "Invalid password"), 401
        
        file_dir = UPLOADS_DIR / file_id
        file_path = file_dir / file_info['current_name']
        
        if not file_path.exists():
            return get_password_page(file_id, file_info['current_name'], "File not found on server"), 500
        
        logger.info(f'File downloaded (password protected): {file_id}')
        
        return send_file(
            str(file_path),
            as_attachment=True,
            download_name=file_info['current_name']
        )
    
    except Exception as e:
        logger.error(f'Download error: {str(e)}')
        return get_password_page(file_id, "Unknown", f"Server error: {str(e)}"), 500

@app.route('/api/files/user', methods=['GET'])
def get_user_files():
    try:
        metadata = load_files_metadata()
        user_files = []
        
        for file_id, file_info in metadata.items():
            if file_info.get('user_ip') == request.remote_addr:
                user_files.append({
                    'file_id': file_id,
                    'name': file_info['current_name'],
                    'size': file_info['size'],
                    'uploaded_at': file_info['uploaded_at'],
                    'is_password_protected': file_info['is_password_protected'],
                    'download_link': f"{TUNNEL_URL}/api/files/download/{file_id}"
                })
        
        return jsonify({'files': user_files}), 200
    
    except Exception as e:
        logger.error(f'Get files error: {str(e)}')
        return jsonify({'error': str(e)}), 500

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
