import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone

from . import llm, search
from .cluster import cluster
from .fetchers import FETCHERS
from .score import is_ai_relevant, score_story
from .store import Store
from .textutil import canonical_url

log = logging.getLogger("ainews")


def collect(cfg):
    items, status = [], {}
    for src in cfg["sources"]:
        name = src.get("name") or src["kind"]
        try:
            got = FETCHERS[src["kind"]](src, cfg)
            items += got
            status[name] = len(got)
        except Exception as e:  # one broken source must never kill the run
            log.warning("source %s failed: %s", name, e)
            status[name] = f"error: {e}"
    return items, status


def within_window(item, hours, now):
    if not item.published_at:
        return True
    dt = datetime.fromisoformat(item.published_at.replace("Z", "+00:00"))
    return now - dt <= timedelta(hours=hours)


def story_json(s, now):
    items = sorted(s.items, key=lambda i: ({"primary": 0, "news": 1, "video": 2, "community": 3}[i.source_type]))
    main = items[0]
    sources, seen = [], set()
    for it in items:
        u = canonical_url(it.url)
        if u not in seen:
            seen.add(u)
            sources.append({"name": it.source, "url": it.url})
    dates = [i.published_at for i in s.items if i.published_at]
    return {
        "id": hashlib.sha1(canonical_url(main.url).encode()).hexdigest()[:12],
        "title": main.title,
        "summary": s.summary or (main.text[:200] if main.text else ""),
        "url": main.url,
        "topic": s.topic,
        "score": round(s.score, 1),
        "sources": sources,
        "signals": s.signals,
        "published_at": min(dates) if dates else None,
        "collected_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def run(cfg, items=None, now=None, dry_run=False):
    now = now or datetime.now(timezone.utc)
    status = {}
    if items is None:
        items, status = collect(cfg)
    items = [i for i in items if within_window(i, cfg["window_hours"], now) and is_ai_relevant(i)]
    stories = [score_story(s, now) for s in cluster(items)]
    stories.sort(key=lambda s: s.score, reverse=True)

    store = Store(os.path.join(cfg["data_dir"], "seen.sqlite"))
    seen_urls, seen_titles = store.recent(cfg.get("dedup_days", 30))
    fresh = [s for s in stories if s.score >= cfg.get("min_score", 15)
             and not store.is_duplicate(s, seen_urls, seen_titles)]
    shortlist = fresh[:cfg.get("shortlist_size", 30)]

    llm_used = False
    if shortlist and llm.configured():
        try:
            verdicts = llm.review(shortlist)
            kept = []
            for i, s in enumerate(shortlist):
                v = verdicts.get(i)
                if v is None:
                    kept.append(s)
                    continue
                if not v.get("keep", True):
                    continue
                s.summary = v.get("summary", "")
                if v.get("topic"):
                    s.topic = v["topic"]
                s.score = 0.6 * s.score + 0.4 * 10 * float(v.get("impact", 5))
                kept.append(s)
            shortlist, llm_used = kept, bool(verdicts)
            shortlist.sort(key=lambda s: s.score, reverse=True)
        except Exception as e:
            log.warning("LLM pass failed, falling back to rules only: %s", e)

    top = shortlist[:cfg.get("max_items", 10)]
    out = {"generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "industry": "ai",
           "window_hours": cfg["window_hours"], "llm_used": llm_used,
           "candidates": len(items), "sources_status": status,
           "items": [story_json(s, now) for s in top]}
    scfg = cfg.get("search", {})
    if scfg.get("enabled") and out["items"]:
        queries = llm.make_queries([(i["title"], i["summary"]) for i in out["items"]])
        search.enrich(out["items"], queries, scfg)
    if not dry_run:
        out_dir = os.path.join(cfg["data_dir"], "daily")
        os.makedirs(out_dir, exist_ok=True)
        day = now.strftime("%Y-%m-%d")
        for name in (f"{day}.json", "latest.json"):
            with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
                json.dump(out, f, indent=2, ensure_ascii=False)
        for s in top:
            store.mark(s, day)
    return out
