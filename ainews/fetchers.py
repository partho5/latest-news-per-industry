"""Source fetchers. Official feeds/APIs only - no HTML scraping."""
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import Item

UA = "ai-news-collector/0.1 (+https://github.com/partho5/latest-news-per-industry)"


def http_get(url, headers=None, timeout=20):
    req = Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urlopen(req, timeout=timeout) as r:
        return r.read()


def get_json(url, headers=None):
    return json.loads(http_get(url, headers))


def _iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        return _iso(parsedate_to_datetime(s))
    except (TypeError, ValueError):
        pass
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return _iso(dt)
    except ValueError:
        return None


def _strip_html(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def parse_feed(xml_bytes, source, source_type):
    """RSS 2.0 and Atom."""
    root = ET.fromstring(xml_bytes)
    out = []
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        f = {}
        for c in el:
            name = _local(c.tag)
            if name == "link":
                f.setdefault("link", c.get("href") or (c.text or "").strip())
            elif name in ("title", "pubDate", "published", "updated", "description", "summary", "content"):
                f.setdefault(name, c.text or "")
        link, title = f.get("link"), _strip_html(f.get("title", ""))
        if not link or not title:
            continue
        date = parse_date(f.get("pubDate") or f.get("published") or f.get("updated"))
        text = _strip_html(f.get("description") or f.get("summary") or f.get("content"))[:600]
        out.append(Item(title, link, source, source_type, date, text))
    return out


def fetch_rss(src, cfg):
    return parse_feed(http_get(src["url"]), src["name"], src.get("type", "news"))


def fetch_hn(src, cfg):
    since = int((datetime.now(timezone.utc) - timedelta(hours=cfg["window_hours"])).timestamp())
    seen, out = set(), []
    for q in src["queries"]:
        params = urlencode({"query": q, "tags": "story", "hitsPerPage": 30,
                            "numericFilters": f"created_at_i>{since},points>{src.get('min_points', 30)}"})
        for h in get_json(f"https://hn.algolia.com/api/v1/search?{params}")["hits"]:
            if h["objectID"] in seen:
                continue
            seen.add(h["objectID"])
            hn_url = f"https://news.ycombinator.com/item?id={h['objectID']}"
            out.append(Item(h["title"], h.get("url") or hn_url, "Hacker News", "community",
                            parse_date(h.get("created_at")), "",
                            {"hn_points": h.get("points") or 0, "hn_comments": h.get("num_comments") or 0,
                             "hn_url": hn_url}))
    return out


def fetch_github(src, cfg):
    """Fast-rising new AI repos (official search API)."""
    since = (datetime.now(timezone.utc) - timedelta(days=src.get("created_within_days", 14))).strftime("%Y-%m-%d")
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    out = []
    for q in src["queries"]:
        params = urlencode({"q": f"{q} created:>{since}", "sort": "stars", "order": "desc", "per_page": 10})
        for r in get_json(f"https://api.github.com/search/repositories?{params}", headers)["items"]:
            if r["stargazers_count"] < src.get("min_stars", 300):
                continue
            out.append(Item(f"{r['full_name']}: {r.get('description') or ''}".strip(": "), r["html_url"],
                            "GitHub", "community", parse_date(r["created_at"]), "",
                            {"stars": r["stargazers_count"]}))
    return out


def fetch_hf(src, cfg):
    """Trending models on the Hugging Face Hub (public API)."""
    params = urlencode({"sort": "trendingScore", "limit": src.get("limit", 25)})
    cutoff = datetime.now(timezone.utc) - timedelta(days=src.get("created_within_days", 10))
    out = []
    for m in get_json(f"https://huggingface.co/api/models?{params}"):
        created = parse_date(m.get("createdAt"))
        if not created or datetime.fromisoformat(created.replace("Z", "+00:00")) < cutoff:
            continue
        out.append(Item(f"New model trending on Hugging Face: {m['id']}",
                        f"https://huggingface.co/{m['id']}", "Hugging Face", "community", created, "",
                        {"likes": m.get("likes", 0), "downloads": m.get("downloads", 0)}))
    return out


def fetch_youtube(src, cfg):
    """Recent uploads of configured channels via YouTube Data API v3 (needs YOUTUBE_API_KEY)."""
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        raise RuntimeError("YOUTUBE_API_KEY not set")
    base = "https://www.googleapis.com/youtube/v3"
    cutoff = datetime.now(timezone.utc) - timedelta(hours=cfg["window_hours"])
    vids = {}
    for handle in src["handles"]:
        ch = get_json(f"{base}/channels?{urlencode({'part': 'snippet,contentDetails,statistics', 'forHandle': handle, 'key': key})}")
        if not ch.get("items"):
            continue
        name = ch["items"][0]["snippet"]["title"]
        subs = int(ch["items"][0].get("statistics", {}).get("subscriberCount", 0))
        uploads = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        pl = get_json(f"{base}/playlistItems?{urlencode({'part': 'snippet', 'playlistId': uploads, 'maxResults': 8, 'key': key})}")
        for it in pl.get("items", []):
            sn = it["snippet"]
            pub = parse_date(sn.get("publishedAt"))
            if pub and datetime.fromisoformat(pub.replace("Z", "+00:00")) >= cutoff:
                vids[sn["resourceId"]["videoId"]] = (name, sn["title"], pub, _strip_html(sn.get("description", ""))[:600], subs)
    out = []
    ids = list(vids)
    for i in range(0, len(ids), 50):
        batch = ids[i:i + 50]
        stats = get_json(f"{base}/videos?{urlencode({'part': 'statistics', 'id': ','.join(batch), 'key': key})}")
        views = {v["id"]: int(v["statistics"].get("viewCount", 0)) for v in stats.get("items", [])}
        for vid in batch:
            name, title, pub, text, subs = vids[vid]
            out.append(Item(title, f"https://www.youtube.com/watch?v={vid}", f"YouTube: {name}", "video",
                            pub, text, {"views": views.get(vid, 0), "subs": subs}))
    return out


FETCHERS = {"rss": fetch_rss, "hn": fetch_hn, "github": fetch_github,
            "huggingface": fetch_hf, "youtube": fetch_youtube}
