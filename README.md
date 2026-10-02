# latest-news-per-industry — `ai-news` branch

Runs once a day on a VPS and writes the 5–10 most significant AI-industry stories to JSON.
Python 3 standard library only (no `pip install`). Official feeds/APIs only — no HTML scraping.

## How a story is chosen
Clustered by event (same URL / near-identical title), then scored 0–100:
cross-outlet coverage (30) + community velocity: HN / GitHub / Hugging Face / YouTube (30) + primary source (15)
+ category weight (15) + freshness (10) − clickbait penalty. Stories already published in the last 30 days are dropped
(SQLite memory). An optional cheap LLM pass over the top ~30 removes quote-only/fluff items and writes a one-line summary.

## Output
`data/daily/YYYY-MM-DD.json` and `data/daily/latest.json`:
`{generated_at, window_hours, llm_used, sources_status, items:[{id,title,summary,url,topic,score,sources[],signals{},published_at,collected_at}]}`
Topics: `model-release | safety-policy | open-source | funding-business | infra-chips | research | other`.

## Deploy (Ubuntu VPS)
```bash
sudo git clone -b ai-news https://github.com/partho5/latest-news-per-industry /opt/news-collector
cd /opt/news-collector
sudo ./deploy/install.sh          # asks for your keys (hidden), writes .env (600), enables the daily timer
python3 -m ainews --dry-run       # try it; check "llm_used" and "sources_status" in the output
```
Runs daily at 08:00 Asia/Dhaka (GMT+6). Logs: `journalctl -u ai-news`.

Keys live only in `.env` on the VPS (git-ignored) — never commit them. `OPENROUTER_API_KEY` is an OpenRouter key; the default
model is `meta-llama/llama-3.1-8b-instruct` (override with `OPENROUTER_MODEL` / `OPENROUTER_BASE_URL` for any OpenAI-compatible
endpoint). `YOUTUBE_API_KEY` enables the YouTube channels; `GITHUB_TOKEN` is optional. A missing key just skips that step,
and an LLM failure falls back to rule-based scoring.
Edit `config.json` to add/remove feeds and YouTube channel handles.

## Tests
`python3 -m unittest discover -s tests`
