from flask import Flask, jsonify, request, send_file
from datetime import datetime
import os
from pathlib import Path
from dotenv import load_dotenv
import logging

load_dotenv()

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

PORT = int(os.getenv('PORT', 5625))
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
LATEST_VERSION = os.getenv('LATEST_VERSION', '0.2.0')
TUNNEL_URL = os.getenv('CLOUDFLARE_TUNNEL_URL', 'https://your-tunnel.example.com')

RELEASES_DIR = Path('releases')
RELEASES_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

@app.route('/versions', methods=['GET'])
def list_versions():
    return jsonify({'versions': sorted(RELEASES_DB.keys()), 'latest': LATEST_VERSION, 'count': len(RELEASES_DB)})

@app.route('/', methods=['GET'])
def index():
    return jsonify({'name': 'OxcyShop Executor Updater Server', 'version': '1.0.0', 'endpoints': {'/updates': 'check-updates', '/download/<path>': 'download-file', '/health': 'health-check', '/versions': 'list-versions'}, 'latest_version': LATEST_VERSION})

if __name__ == '__main__':
    logger.info(f'Starting on 0.0.0.0:{PORT}')
    app.run(host='0.0.0.0', port=PORT, debug=DEBUG)
