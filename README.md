# latest-news-per-industry — `ai-news` branch

## Goal
Every day, deliver to me (on Telegram, and as JSON on the VPS) the **5–10 AI-industry stories that matter most** —
the ones many credible people are genuinely talking about: a major model/product launch, an open-weights release
that changes what's possible, a credible safety/policy warning, a big funding or regulatory move. For each story,
also send 1–2 links to *other* outlets covering the same thing, so I can read a second source.
Later, the same approach is reused per industry on its own branch (`fintech-news`, …); this branch is AI only.

## Philosophy
- **Signal over noise.** A story matters because of how widely and independently it is being discussed, not because
  a famous person said something. A CEO/celebrity quote with no new fact is noise. A real launch, release, research
  result, policy decision or credible warning is signal.
- **Trustworthy and legitimate sources only.** Official feeds and APIs (RSS, Hacker News, GitHub, Hugging Face,
  YouTube Data API, lab/company blogs). No scraping of sites that don't allow it. The one exception is the
  DuckDuckGo related-links search, which is an unofficial placeholder meant to be swapped for an official search API.
- **Never repeat yourself.** The same story must not be sent twice, within a day (merge duplicates across outlets)
  or across days (remember what was already sent).
- **Few and compact beats many.** 5–10 items a day, one short summary each, one link each.
- **Cheap and boring to run.** One run per day, standard-library Python, a very cheap LLM (a fraction of a cent per day).
- **Never break the whole run for an optional part.** If the LLM, the search, Telegram, or any single source fails,
  log it and carry on; the JSON is always written. Fail loudly in the logs, softly in the output.
- **Secrets stay out of git.** Keys live only in `.env` on the VPS (mode 600). Never paste keys or the Telegram
  session string into chats, issues or commits. If one leaks, revoke it.

## Steps (Ubuntu VPS, clone → running)

### 1. Get your keys
All optional; a missing key just skips that feature.
| Key | Where to get it | Used for |
|---|---|---|
| `OPENROUTER_API_KEY` | openrouter.ai → Keys (add a few dollars of credit) | filtering fluff, summaries, search queries |
| `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` | my.telegram.org → API development tools | Telegram digest |
| `TELEGRAM_SESSION` | Telethon StringSession made with the *same* api_id/api_hash | Telegram digest |
| `YOUTUBE_API_KEY` | Google Cloud Console → enable YouTube Data API v3 → API key | AI-news YouTube channels |

### 2. Install system packages
```bash
sudo apt update && sudo apt install -y git python3 python3-venv
```

### 3. Clone the branch
```bash
sudo git clone -b ai-news https://github.com/partho5/latest-news-per-industry /opt/news-collector
cd /opt/news-collector
```

### 4. Run the installer
```bash
sudo ./deploy/install.sh
```
It creates a virtualenv, installs dependencies, asks for the keys (hidden input; Enter skips), writes `.env`
(mode 600), and enables a systemd timer that runs daily at **08:00 Asia/Dhaka (GMT+6)**.

### 5. Verify with a dry run
```bash
sudo .venv/bin/python -m ainews --dry-run
```
Prints the JSON; sends nothing and writes nothing. Check that:
- `"llm_used": true`
- every entry in `sources_status` is a number, not `error: …`
- each item has a `summary` and a `related` list

### 6. Do a real run
```bash
sudo systemctl start ai-news
journalctl -u ai-news -n 40 --no-pager
```
Expect `wrote N items` and `telegram sent=True`, and the messages in Telegram (Saved Messages by default,
or `TELEGRAM_CHAT`). Output is in `data/daily/`. With no news worth sending, nothing is sent.

### 7. Day-to-day
```bash
systemctl list-timers ai-news.timer                     # next run
journalctl -u ai-news -f                                # logs
git pull && .venv/bin/pip install -r requirements.txt   # update to latest
```

## If something is wrong (steps for whoever debugging on the VPS)
1. Read the logs: `journalctl -u ai-news -n 100 --no-pager`. Each optional part logs a warning when it fails.
2. Run `sudo .venv/bin/python -m ainews --dry-run` and read `sources_status`, `llm_used`, and the items.
3. Fix the smallest thing that explains the symptom, keeping the philosophy above (never let an optional part break the run).
4. Run the tests: `.venv/bin/python -m unittest discover -s tests` (network and Telegram are mocked).
5. Re-run the dry run, then a real run; confirm the symptom is gone.
6. Commit with a clear message and push to `ai-news`. Never commit `.env` or any key.
