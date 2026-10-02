#!/usr/bin/env bash
# Run on the VPS from inside the checkout:  sudo ./deploy/install.sh
# Creates the venv, installs deps, writes .env (mode 600) from your answers, installs the daily 08:00 Asia/Dhaka timer.
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"

python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt

if [ ! -f .env ]; then
  umask 077
  cp .env.example .env
  ask() {  # ask VAR "prompt" [hidden]
    local v
    if [ "${3:-}" = hidden ]; then read -rsp "$2 (Enter to skip): " v; echo; else read -rp "$2 (Enter to skip): " v; fi
    [ -n "$v" ] && sed -i "s|^$1=.*|$1=$v|" .env
    return 0
  }
  ask OPENROUTER_API_KEY "OpenRouter API key" hidden
  ask TELEGRAM_API_ID "Telegram api_id"
  ask TELEGRAM_API_HASH "Telegram api_hash" hidden
  ask TELEGRAM_SESSION "Telegram StringSession" hidden
  ask YOUTUBE_API_KEY "YouTube Data API key" hidden
  echo "wrote $DIR/.env (mode 600)"
fi
chmod 600 .env

sed "s|/opt/news-collector|$DIR|g" deploy/ai-news.service > /etc/systemd/system/ai-news.service
cp deploy/ai-news.timer /etc/systemd/system/ai-news.timer
systemctl daemon-reload
systemctl enable --now ai-news.timer
echo "Installed. Next run:"; systemctl list-timers ai-news.timer --no-pager | head -3
echo "Test now:  $DIR/.venv/bin/python -m ainews --dry-run     (real run + Telegram: sudo systemctl start ai-news)"
