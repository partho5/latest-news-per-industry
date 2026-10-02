#!/usr/bin/env bash
# Run on the VPS from inside the checkout:  sudo ./deploy/install.sh
# Prompts for keys (input hidden), writes .env with 600 permissions, installs a daily 08:00 Asia/Dhaka timer.
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"

if [ ! -f .env ]; then
  read -rsp "OpenRouter API key (LLM_API_KEY, Enter to skip): " LLM; echo
  read -rsp "YouTube Data API key (Enter to skip): " YT; echo
  umask 077
  cp .env.example .env
  sed -i "s|^LLM_API_KEY=.*|LLM_API_KEY=$LLM|; s|^YOUTUBE_API_KEY=.*|YOUTUBE_API_KEY=$YT|" .env
  echo "wrote $DIR/.env (mode 600)"
fi
chmod 600 .env

sed "s|/opt/news-collector|$DIR|g" deploy/ai-news.service > /etc/systemd/system/ai-news.service
cp deploy/ai-news.timer /etc/systemd/system/ai-news.timer
systemctl daemon-reload
systemctl enable --now ai-news.timer
echo "Installed. Next run:"; systemctl list-timers ai-news.timer --no-pager | head -3
echo "Try it now:  python3 -m ainews --dry-run     (or: sudo systemctl start ai-news)"
