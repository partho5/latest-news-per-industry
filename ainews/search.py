"""Related-news lookup via DuckDuckGo's HTML endpoint (placeholder implementation).

NOTE: html.duckduckgo.com is not an official API - it can CAPTCHA/block a VPS IP or change layout.
Everything here is best-effort: on any failure we return [] and the digest is still sent.
To switch to an official API (e.g. Brave Search), replace `search_ddg` only; the rest keeps working.
"""
import logging
import re
import time
import urllib.parse
import urllib.request

from .textutil import domain, tokens

log = logging.getLogger("ainews")

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/122.0.0.0 Safari/537.36")
NEWS_DOMAINS = {"reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "theverge.com", "techcrunch.com",
                "arstechnica.com", "wired.com", "technologyreview.com", "venturebeat.com", "cnbc.com",
                "bloomberg.com", "ft.com", "nytimes.com", "theguardian.com", "wsj.com", "axios.com",
                "zdnet.com", "engadget.com", "theinformation.com", "washingtonpost.com"}
SKIP_DOMAINS = {"youtube.com", "youtu.be", "reddit.com", "x.com", "twitter.com", "facebook.com",
                "instagram.com", "tiktok.com", "linkedin.com", "pinterest.com", "quora.com"}

_BLOCK_RE = re.compile(r'<div[^>]*class="([^"]*\bresult\b[^"]*)"[^>]*>(.*?)(?=<div[^>]*class="[^"]*\bresult\b[^"]*"|\Z)', re.S)
_LINK_RE = re.compile(r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_SNIP_RE = re.compile(r'<(?:a|td|div)[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</(?:a|td|div)>', re.S)


def _clean(html):
    import html as h
    return h.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or ""))).strip()


def parse_ddg(html, max_results=20):
    out = []
    for cls, block in _BLOCK_RE.findall(html):
        if "result--ad" in cls:
            continue
        m = _LINK_RE.search(block)
        if not m:
            continue
        url = m.group(1)
        if "uddg=" in url:
            q = re.search(r"uddg=([^&]+)", url)
            url = urllib.parse.unquote(q.group(1)) if q else url
        if url.startswith("//"):
            url = "https:" + url
        if "duckduckgo.com/y.js" in url or not url.startswith("http"):
            continue
        s = _SNIP_RE.search(block)
        out.append({"title": _clean(m.group(2)), "url": url, "snippet": _clean(s.group(1)) if s else ""})
        if len(out) >= max_results:
            break
    return out


def search_ddg(query, max_results=20, timeout=20):
    if not query or not query.strip():
        raise ValueError("query must be non-empty")
    req = urllib.request.Request(
        "https://html.duckduckgo.com/html/",
        data=urllib.parse.urlencode({"q": query.strip()}).encode(),
        headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return parse_ddg(r.read().decode("utf-8", "replace"), max_results)


def _root(host):
    parts = host.split(".")
    return ".".join(parts[-3:] if parts[-2:-1] and len(parts[-2]) <= 3 and len(parts[-1]) == 2 else parts[-2:])


def pick_related(results, query, own_urls, per_item=2, min_relevance=0.3):
    """Most relevant results, one per site, excluding the story's own sites and social media."""
    own = {_root(domain(u)) for u in own_urls}
    q = tokens(query)
    scored, seen = [], set()
    for r in results:
        root = _root(domain(r["url"]))
        if root in own or root in SKIP_DOMAINS or root in seen:
            continue
        rel = len(q & tokens(r["title"] + " " + r["snippet"])) / max(1, len(q))
        if rel < min_relevance:
            continue
        seen.add(root)
        scored.append((rel + (0.2 if root in NEWS_DOMAINS else 0), r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"title": r["title"], "url": r["url"], "snippet": r["snippet"][:220]} for _, r in scored[:per_item]]


def enrich(items, queries, cfg, search=None, sleep=None):
    """Add `search_query` and `related` to each item dict. Never raises."""
    search = search or search_ddg   # resolved at call time so the backend can be swapped/mocked
    sleep = sleep or time.sleep
    per_item = cfg.get("per_item", 2)
    for i, item in enumerate(items):
        q = queries.get(i) or f"{item['title']} news"
        item["search_query"], item["related"] = q, []
        try:
            res = search(q)
            item["related"] = pick_related(res, q, [s["url"] for s in item["sources"]], per_item)
        except Exception as e:
            log.warning("related search failed for %r: %s", q, e)
        if i < len(items) - 1:
            sleep(cfg.get("delay_seconds", 3))
    return items
