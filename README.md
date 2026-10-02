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
cd /opt/news-collector && cp .env.example .env   # fill in keys you have; all optional
python3 -m ainews --dry-run                       # try it
sudo cp deploy/ai-news.* /etc/systemd/system/
sudo systemctl enable --now ai-news.timer         # daily 08:00 Asia/Dhaka
```
Keys (`.env`): `YOUTUBE_API_KEY` (YouTube Data API v3), `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY`
(any OpenAI-compatible endpoint), `GITHUB_TOKEN` (optional, higher rate limit). Missing keys just skip that step.
Edit `config.json` to add/remove feeds and YouTube channel handles.

## Tests
`python3 -m unittest discover -s tests`
