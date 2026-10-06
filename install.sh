#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ "$(id -u)" -ne 0 ]; then
  echo "Execute como root: sudo ./install.sh"
  exit 1
fi

apt-get update -y
apt-get install -y python3 python3-venv python3-pip curl unzip openssl

[ -f .env ] || cp .env.example .env

read -r -p "Token do BOT do Telegram: " BOT_TOKEN
read -r -p "Seu ID numérico do Telegram (admin): " ADMIN_IDS

MASTER_KEY=$(openssl rand -hex 32)
export BOT_TOKEN ADMIN_IDS MASTER_KEY
python3 - <<'PY'
from pathlib import Path
import os, re
p=Path('.env')
s=p.read_text()
vals={'BOT_TOKEN':os.environ['BOT_TOKEN'],'ADMIN_IDS':os.environ['ADMIN_IDS'],'MASTER_KEY':os.environ['MASTER_KEY']}
for k,v in vals.items():
    s=re.sub(rf'^{k}=.*$', f'{k}={v}', s, flags=re.M)
p.write_text(s)
PY

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
mkdir -p data logs
python -m app.db

SERVICE=/etc/systemd/system/lomadee-auto-bot.service
APP_DIR="$(pwd)"
cat > "$SERVICE" <<UNIT
[Unit]
Description=Lomadee Auto Offers Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python -m app.bot
Restart=always
RestartSec=5
EnvironmentFile=$APP_DIR/.env

[Install]
WantedBy=multi-user.target
UNIT

chmod 600 .env
systemctl daemon-reload
systemctl enable lomadee-auto-bot
systemctl restart lomadee-auto-bot
sleep 2
systemctl --no-pager --full status lomadee-auto-bot || true

echo
echo "=============================================="
echo " LOMADEE AUTO BOT INSTALADO"
echo "=============================================="
echo "Abra o Telegram e envie /start para o bot."
echo "Logs: journalctl -u lomadee-auto-bot -f"
echo "=============================================="
