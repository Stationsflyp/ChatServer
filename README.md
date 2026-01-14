# OxcyShop Executor - Updater Server

Python Flask server for distributing OxcyShop Executor updates via Cloudflare Tunnel.

## Quick Start

**Windows:** Double-click `start.bat`

**Linux/Mac:** Run `./start.sh`

## Manual Setup

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your Cloudflare tunnel URL
python app.py
```

## Configuration

Edit `.env`:
```
PORT=5625
DEBUG=False
LATEST_VERSION=0.2.0
CLOUDFLARE_TUNNEL_URL=https://your-tunnel.trycloudflare.com
```

## Add Release Files

Place MSI files in `releases/`:
```
releases/
├── 0.1.0/
│   └── OxcyShop-Executor_0.1.0_x64_en-US.msi
└── 0.2.0/
    └── OxcyShop-Executor_0.2.0_x64_en-US.msi
```

## API Endpoints

- `GET /` - Server info
- `GET /updates?version=X&target=windows-x86_64` - Check updates
- `GET /download/<path>` - Download file
- `GET /health` - Health check
- `GET /versions` - List versions

## VPS Deployment

### 1. Clone Repository
```bash
git clone <your-repo-url>
cd updater_server
```

### 2. Install & Configure
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your Cloudflare tunnel URL
```

### 3. Set Up Cloudflare Tunnel
```bash
curl -L --output cloudflared.tgz https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.tgz
tar -xzf cloudflared.tgz
sudo mv cloudflared /usr/local/bin/
cloudflared tunnel create executor-updates
cloudflared tunnel route dns executor-updates <your-domain.com>
```

### 4. Run Server

Using systemd:
```bash
sudo nano /etc/systemd/system/executor-updater.service
# Add service config
sudo systemctl enable executor-updater
sudo systemctl start executor-updater
```

Or directly:
```bash
nohup python app.py > updater.log 2>&1 &
```

## Security

- Use HTTPS (Cloudflare tunnel)
- Keep private key secure
- Validate release signatures
- Add authentication for admin endpoints

## Troubleshooting

```bash
# Health check
curl http://localhost:5625/health

# List versions
curl http://localhost:5625/versions

# Check logs
tail -f updater.log
```

## Environment Variables

- `PORT` - Server port (default: 5625)
- `DEBUG` - Enable debug mode (default: False)
- `LATEST_VERSION` - Latest version available (default: 0.2.0)
- `CLOUDFLARE_TUNNEL_URL` - Your Cloudflare tunnel URL

## License

Same as OxcyShop Executor
