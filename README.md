# latest-news-per-industry — `ai-news` branch

Once a day on a VPS: collects AI-industry news from official feeds/APIs, keeps the 5–10 most significant stories,
writes them to JSON, and sends them to Telegram — each with 1–2 related links found by a web search.

## How a story is chosen
Items are clustered by event (same URL / near-identical title), then scored 0–100:
cross-outlet coverage (30) + community velocity — HN / GitHub / Hugging Face / YouTube (30) + primary source (15)
+ category weight (15) + freshness (10) − clickbait penalty. Anything published in the last 30 days is dropped
(SQLite memory). A cheap LLM pass over the top ~30 removes quote-only/fluff items and writes one-line summaries.
Then, per story, the LLM writes a search query, DuckDuckGo is searched, and the 1–2 most relevant results from
*other* sites are attached. A failure in any optional step (LLM, search, Telegram) never stops the run.

## Output
`data/daily/YYYY-MM-DD.json` and `data/daily/latest.json`:
`{generated_at, window_hours, llm_used, sources_status, items:[{id,title,summary,url,topic,score,sources[],signals{},
search_query,related[{title,url,snippet}],published_at,collected_at}]}`
Topics: `model-release | safety-policy | open-source | funding-business | infra-chips | research | other`.

---

## Deployment guide (Ubuntu VPS, from clone to running)

### 0. Get your keys first
| Key | Where | Needed for |
|---|---|---|
| `OPENROUTER_API_KEY` | openrouter.ai → Keys (add a few dollars of credit) | LLM filtering, summaries, search queries |
| `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` | my.telegram.org → API development tools | Telegram digest |
| `TELEGRAM_SESSION` | A Telethon **StringSession** generated with the *same* api_id/api_hash (`StringSession.save()` after logging in with your OTP) | Telegram digest |
| `YOUTUBE_API_KEY` | Google Cloud Console → enable *YouTube Data API v3* → Credentials → API key | YouTube channels |

All are optional: a missing key just skips that step. **A StringSession grants full access to your Telegram account.**
Never paste it into chats/issues/commits; if it leaks, revoke it in Telegram → Settings → Devices.

### 1. Install system packages
```bash
sudo apt update && sudo apt install -y git python3 python3-venv
```

### 2. Clone the `ai-news` branch
```bash
sudo git clone -b ai-news https://github.com/partho5/latest-news-per-industry /opt/news-collector
cd /opt/news-collector
```

### 3. Run the installer
```bash
sudo ./deploy/install.sh
```
It creates `.venv`, installs `telethon`, asks for the keys above (input hidden; press Enter to skip any), writes
`.env` with mode 600, and installs + starts a systemd timer that runs daily at **08:00 Asia/Dhaka (GMT+6)**.
Prefer manual setup? `cp .env.example .env`, edit it, then copy `deploy/ai-news.{service,timer}` to
`/etc/systemd/system/`, and `sudo systemctl enable --now ai-news.timer`.

### 4. Verify
```bash
sudo .venv/bin/python -m ainews --dry-run     # prints the JSON; sends nothing, writes nothing
```
Check in the output: `"llm_used": true`; `sources_status` shows a count (not `error: …`) for each source;
each item has a `related` list. Then run for real (writes JSON, updates dedup memory, sends Telegram):
```bash
sudo systemctl start ai-news && journalctl -u ai-news -n 30 --no-pager
```
You should see `wrote N items` and `telegram sent=True`.

### 5. Operate
```bash
systemctl list-timers ai-news.timer      # next run
journalctl -u ai-news -f                 # logs
cd /opt/news-collector && sudo git pull && sudo .venv/bin/pip install -r requirements.txt   # update
```

### Configuration (`config.json`)
Feeds and YouTube channel handles (`sources`), `max_items`, `window_hours`, `min_score`, `dedup_days`,
`search` (`enabled`, `per_item`, `delay_seconds`) and `telegram.enabled`.
Telegram messages go to `TELEGRAM_CHAT` (default `me` = Saved Messages; or a chat id / `@username`). No news → no message.

### Notes
- Related-link search uses DuckDuckGo's unofficial HTML endpoint (`ainews/search.py`). It can be rate-limited or change
  without notice; if it breaks, only the `related` links disappear. Swap `search_ddg` for an official search API when needed.
- Only `OPENROUTER_API_KEY` is needed for the LLM step; override `OPENROUTER_MODEL` / `OPENROUTER_BASE_URL` for other models.

## Tests
`python3 -m unittest discover -s tests` (Telegram and network are mocked)
