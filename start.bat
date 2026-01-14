@echo off
echo Starting OxcyShop Updater Server...
if not exist venv (
    python -m venv venv
)
call venv\Scripts\activate.bat
pip install -r requirements.txt -q
echo.
echo OxcyShop Executor Updater Server
echo Server: http://localhost:5625
echo.
python app.py