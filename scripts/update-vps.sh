#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

git pull --ff-only
. .venv/bin/activate
pip install -r requirements.txt
systemctl restart lomadee-auto-bot
systemctl --no-pager --full status lomadee-auto-bot
