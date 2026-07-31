#!/bin/bash
# Minimal troll agent-server setup for a fresh Dedalus Machine.
# Installs the FastAPI server's Python deps, registers it as a systemd
# service, and waits for it to answer on localhost:8000/health.

set -euo pipefail

APP_DIR="/home/machine/troll_app"
LOG_FILE="$APP_DIR/server.log"
PORT=8000
PACKAGES="fastapi uvicorn dedalus-labs pydantic"

echo "Installing Python packages..."
if ! python3 -m pip --version >/dev/null 2>&1; then
    echo "pip missing - installing python3-pip via apt..."
    export DEBIAN_FRONTEND=noninteractive
    export NEEDRESTART_SUSPEND=1
    WAIT_START=$(date +%s)
    while fuser /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/cache/apt/archives/lock >/dev/null 2>&1; do
        if [ $(( $(date +%s) - WAIT_START )) -ge 300 ]; then
            echo "WARN: dpkg lock still held after 300s - proceeding"
            break
        fi
        sleep 5
    done
    apt-get update -qq
    apt-get install -y -qq --no-install-recommends python3-pip
fi

python3 -m pip install -q --no-cache-dir --ignore-installed typing_extensions 2>/dev/null \
  || python3 -m pip install -q --no-cache-dir --break-system-packages --ignore-installed typing_extensions
python3 -m pip install -q --no-cache-dir $PACKAGES 2>/dev/null \
  || python3 -m pip install -q --no-cache-dir --break-system-packages $PACKAGES

echo "Installing troll-server.service..."
echo "DEDALUS_API_KEY=${DEDALUS_API_KEY}" > /etc/troll-server.env
chmod 600 /etc/troll-server.env

cat >/etc/systemd/system/troll-server.service <<'SYSTEMD_UNIT'
[Unit]
Description=Troll FastAPI agent server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/machine/troll_app
EnvironmentFile=/etc/troll-server.env
ExecStart=/usr/bin/python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=2
StandardOutput=append:/home/machine/troll_app/server.log
StandardError=append:/home/machine/troll_app/server.log

[Install]
WantedBy=multi-user.target
SYSTEMD_UNIT

systemctl daemon-reload
systemctl enable --now troll-server
echo "troll-server.service enabled"

echo "Waiting for server health check..."
for i in $(seq 1 30); do
    if curl -sf "http://localhost:$PORT/health" > /dev/null 2>&1; then
        echo "Server running on port $PORT"
        exit 0
    fi
    sleep 1
done

echo "ERROR: Server failed to start"
tail -30 "$LOG_FILE" || echo "(no log file)"
exit 1
