#!/bin/bash
# Sets up the CodeSite runner on a new Railway sandbox (see runcode/README.md)
set -e
export DEBIAN_FRONTEND=noninteractive   # don't stop for installer questions

read -s -p "Paste RUNNER_TOKEN: " RUNNER_TOKEN; echo
export RUNNER_TOKEN

# Start Docker if it isn't running, and download the image student code runs in
docker info > /dev/null 2>&1 || { setsid nohup dockerd > /var/log/dockerd.log 2>&1 & sleep 5; }
docker pull -q python:3.12-slim

# Install Flask and gunicorn
apt-get update -qq && apt-get install -y -qq python3-venv > /dev/null
cd /opt/codesite/runcode
python3 -m venv venv
venv/bin/pip install -q -r requirements.txt

# Start the runner in the background (keeps running after SSH closes)
pkill -f gunicorn || true
setsid nohup venv/bin/gunicorn --bind [::]:8000 --threads 8 --timeout 60 runner:app > /var/log/codesite-runner.log 2>&1 < /dev/null &
sleep 3

# Test it, then print the address for Railway
curl -s -X POST http://127.0.0.1:8000/run -H "X-Runner-Token: $RUNNER_TOKEN" -H "Content-Type: application/json" -d "{\"code\":\"print(1+1)\"}"; echo
echo "RUNNER_URL=http://[$(ip -6 addr | grep -o "fd12:[0-9a-f:]*" | head -1)]:8000"