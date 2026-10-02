"""Telegram digest via a user StringSession (Telethon, imported lazily so the rest has no dependencies).
Env: TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION, TELEGRAM_CHAT (default "me" = Saved Messages)."""
import asyncio
import html
import logging
import os

log = logging.getLogger("ainews")
LIMIT = 4000  # Telegram caps messages at 4096 chars


def configured():
    return all(os.environ.get(k) for k in ("TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_SESSION"))


def _a(url, text):
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(text)}</a>'


def format_item(n, item):
    parts = [f"<b>{n}. {html.escape(item['title'])}</b>"]
    meta = f"{item['topic']} · score {item['score']:.0f}"
    parts.append(f"<i>{html.escape(meta)}</i>")
    if item.get("summary"):
        parts.append(html.escape(item["summary"]))
    parts.append(_a(item["url"], "Read more"))
    related = item.get("related") or []
    if related:
        parts.append("\n<b>Related coverage</b>")
        for r in related:
            line = _a(r["url"], r["title"] or r["url"])
            if r.get("snippet"):
                line += "\n" + html.escape(r["snippet"])
            parts.append(line)
    text = "\n".join(parts)
    return text if len(text) <= LIMIT else text[:LIMIT - 1] + "…"


def build_messages(out):
    return [format_item(i, it) for i, it in enumerate(out["items"], 1)]


async def _send(messages, delay=1.0):
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    chat = os.environ.get("TELEGRAM_CHAT") or "me"
    if chat.lstrip("-").isdigit():
        chat = int(chat)
    client = TelegramClient(StringSession(os.environ["TELEGRAM_SESSION"]),
                            int(os.environ["TELEGRAM_API_ID"]), os.environ["TELEGRAM_API_HASH"])
    async with client:
        for m in messages:
            await client.send_message(chat, m, parse_mode="html", link_preview=False)
            await asyncio.sleep(delay)


def send_digest(out):
    """One message per item. Quiet days (no items) send nothing. Never raises."""
    if not out["items"] or not configured():
        return False
    try:
        asyncio.run(_send(build_messages(out)))
        return True
    except Exception as e:
        log.warning("Telegram send failed: %s", e)
        return False
