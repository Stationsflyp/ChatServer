#!/bin/bash
echo 'Starting OxcyShop Updater Server...'
if [ ! -d 'venv' ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt -q
echo ''
echo 'OxcyShop Executor Updater Server'
echo 'Server: http://0.0.0.0:5625'
echo ''
python app.py