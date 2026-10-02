"""SQLite memory of what we already published, for cross-day de-duplication."""
import sqlite3
from datetime import datetime, timedelta, timezone

from .textutil import canonical_url, tokens, similar_titles


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS seen (url TEXT, title TEXT, day TEXT)")
        self.db.execute("CREATE INDEX IF NOT EXISTS seen_day ON seen(day)")

    def recent(self, days):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = self.db.execute("SELECT url, title FROM seen WHERE day >= ?", (cutoff,)).fetchall()
        return {r[0] for r in rows}, [tokens(r[1]) for r in rows if r[1]]

    def is_duplicate(self, story, seen_urls, seen_titles, threshold=0.6):
        for it in story.items:
            if canonical_url(it.url) in seen_urls:
                return True
            t = tokens(it.title)
            if any(similar_titles(t, st, threshold) for st in seen_titles):
                return True
        return False

    def mark(self, story, day):
        rows = [(canonical_url(it.url), it.title, day) for it in story.items]
        self.db.executemany("INSERT INTO seen VALUES (?,?,?)", rows)
        self.db.commit()
