import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

from ainews import llm, pipeline
from ainews.cluster import cluster
from ainews.fetchers import parse_feed
from ainews.models import Item
from ainews.textutil import canonical_url

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
T = "2026-10-02T06:00:00Z"


def fixtures():
    gates = [Item("Bill Gates warns AI could be misused to kill billions", f"https://{d}/gates", n, "news", T)
             for d, n in [("techcrunch.com", "TechCrunch"), ("theverge.com", "The Verge"),
                          ("wired.com", "WIRED"), ("arstechnica.com", "Ars Technica")]]
    gates.append(Item("Bill Gates warns AI could kill billions of people", "https://news.ycombinator.com/item?id=1",
                      "Hacker News", "community", T, "", {"hn_points": 900, "hn_comments": 600}))
    qwen = [Item("Qwen 3.5 runs CPU-only with open weights", "https://huggingface.co/Qwen/Qwen3.5", "Hugging Face",
                 "community", T, "", {"likes": 800}),
            Item("Qwen 3.5 now runs on CPU only, open weights released", "https://news.ycombinator.com/item?id=2",
                 "Hacker News", "community", T, "", {"hn_points": 700, "hn_comments": 300})]
    claude = [Item("Anthropic launches Claude cloud sessions", "https://anthropic.com/news/cloud-sessions",
                   "Anthropic", "primary", T),
              Item("Anthropic launches cloud sessions for Claude Code", "https://theverge.com/claude", "The Verge", "news", T)]
    fluff = [Item("Top 10 AI tools you won't believe", "https://x.com/a", "WIRED", "news", T),
             Item("Nvidia CEO says AI is great", "https://x.com/b", "Blog", "news", T)]
    old = [Item("OpenAI launches old model", "https://openai.com/old", "OpenAI", "primary", "2026-09-01T00:00:00Z")]
    return gates + qwen + claude + fluff + old


class Tests(unittest.TestCase):
    def cfg(self, d):
        return {"window_hours": 36, "max_items": 10, "min_score": 15, "shortlist_size": 30, "dedup_days": 30,
                "data_dir": d, "sources": []}

    def test_canonical_url(self):
        self.assertEqual(canonical_url("https://www.Example.com/a/?utm_source=x&id=2#frag"),
                         "https://example.com/a?id=2")

    def test_cluster_merges_same_event(self):
        stories = cluster([i for i in fixtures() if "Gates" in i.title])
        self.assertEqual(len(stories), 1)
        self.assertEqual(len(stories[0].items), 5)

    def test_ranking_and_filters(self):
        with tempfile.TemporaryDirectory() as d:
            out = pipeline.run(self.cfg(d), items=fixtures(), now=NOW, dry_run=True)
        titles = [i["title"] for i in out["items"]]
        self.assertTrue(any("Gates" in t for t in titles))
        self.assertTrue(any("Qwen" in t for t in titles))
        self.assertTrue(any("cloud sessions" in t for t in titles))
        self.assertFalse(any("old model" in t for t in titles))       # outside window
        self.assertFalse(any("Top 10" in t for t in titles))          # clickbait
        gates = next(i for i in out["items"] if "Gates" in i["title"])
        self.assertEqual(gates["topic"], "safety-policy")
        self.assertEqual(gates["signals"]["outlets"], 4)

    def test_cross_day_dedup(self):
        with tempfile.TemporaryDirectory() as d:
            first = pipeline.run(self.cfg(d), items=fixtures(), now=NOW)
            self.assertTrue(first["items"])
            second = pipeline.run(self.cfg(d), items=fixtures(), now=NOW)
            self.assertEqual(second["items"], [])
            self.assertTrue(os.path.exists(os.path.join(d, "daily", "latest.json")))

    def test_llm_filters_and_summarises(self):
        verdicts = lambda stories: {i: {"keep": "Gates" not in s.items[0].title, "impact": 9,
                                        "summary": "s", "topic": "other"} for i, s in enumerate(stories)}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(llm, "configured", return_value=True), \
                mock.patch.object(llm, "review", side_effect=verdicts):
            out = pipeline.run(self.cfg(d), items=fixtures(), now=NOW, dry_run=True)
        self.assertTrue(out["llm_used"])
        self.assertFalse(any("Gates" in i["title"] for i in out["items"]))

    def test_llm_failure_falls_back(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(llm, "configured", return_value=True), \
                mock.patch.object(llm, "review", side_effect=RuntimeError("boom")):
            out = pipeline.run(self.cfg(d), items=fixtures(), now=NOW, dry_run=True)
        self.assertFalse(out["llm_used"])
        self.assertTrue(out["items"])

    def test_llm_batches_and_survives_partial_failure(self):
        from ainews.models import Story
        stories = [Story(items=[Item(f"t{i}", f"https://a.com/{i}", "S", "news", T)]) for i in range(25)]
        calls = []

        def chat(prompt):
            calls.append(prompt)
            if len(calls) == 2:
                raise RuntimeError("bad batch")
            ids = [int(x) for x in __import__("re").findall(r"^\[(\d+)\]", prompt, __import__("re").M)]
            return json.dumps([{"id": i, "keep": True, "impact": 5} for i in ids])
        with mock.patch.object(llm, "_chat", chat):
            v = llm.review(stories)
        self.assertEqual(len(calls), 3)
        self.assertEqual(sorted(v), list(range(10)) + list(range(20, 25)))

    def test_llm_only_needs_api_key(self):
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "k"}, clear=True):
            self.assertTrue(llm.configured())
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(llm.configured())

    def test_parse_verdicts_tolerates_prose(self):
        v = llm.parse_verdicts('Sure!\n```json\n[{"id": 0, "keep": true, "impact": 7}]\n```')
        self.assertEqual(v[0]["impact"], 7)

    def test_parse_rss_and_atom(self):
        rss = b"""<rss><channel><item><title>A &amp; B</title><link>https://a.com/1</link>
        <pubDate>Fri, 02 Oct 2026 06:00:00 GMT</pubDate><description>&lt;p&gt;hi&lt;/p&gt;</description></item></channel></rss>"""
        atom = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>T</title>
        <link href="https://a.com/2"/><updated>2026-10-02T06:00:00Z</updated></entry></feed>"""
        self.assertEqual(parse_feed(rss, "x", "news")[0].published_at, "2026-10-02T06:00:00Z")
        self.assertEqual(parse_feed(atom, "x", "news")[0].url, "https://a.com/2")

    def test_youtube_fetch_and_relative_views(self):
        from ainews import fetchers, score
        pub = "2026-10-02T06:00:00Z"

        def fake(url, headers=None):
            if "/channels" in url:
                return {"items": [{"snippet": {"title": "Matt Wolfe"}, "statistics": {"subscriberCount": "1000"},
                                   "contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]}
            if "/playlistItems" in url:
                return {"items": [{"snippet": {"title": "Qwen 3.5 is wild", "publishedAt": pub,
                                               "description": "AI model news", "resourceId": {"videoId": "v1"}}}]}
            return {"items": [{"id": "v1", "statistics": {"viewCount": "500"}}]}
        cfg = {"window_hours": 48 * 365}
        with mock.patch.dict(os.environ, {"YOUTUBE_API_KEY": "k"}), mock.patch.object(fetchers, "get_json", fake):
            vids = fetchers.fetch_youtube({"handles": ["@mreflow"]}, cfg)
        self.assertEqual(vids[0].url, "https://www.youtube.com/watch?v=v1")
        self.assertEqual(vids[0].source, "YouTube: Matt Wolfe")
        self.assertEqual(score.engagement(vids[0]), 1500)  # 500 views / 1000 subs * 3000


DDG_HTML = """
<div class="result results_links results_links_deep web-result"><div class="result__body">
<h2><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.reuters.com%2Ftech%2Fgates-ai&rut=x">Gates warns <b>AI</b> risks</a></h2>
<a class="result__snippet" href="x">Bill Gates said <b>AI</b> could be misused to cause mass harm.</a></div></div>
<div class="result result--ad"><div class="result__body"><a class="result__a" href="https://duckduckgo.com/y.js?ad=1">Buy stuff</a>
<a class="result__snippet">ad</a></div></div>
<div class="result results_links web-result"><div class="result__body">
<a class="result__a" href="https://techcrunch.com/gates">Gates on AI risk (no snippet below)</a></div></div>
<div class="result results_links web-result"><div class="result__body">
<a class="result__a" href="https://www.youtube.com/watch?v=1">Gates AI warning video</a>
<a class="result__snippet">Bill Gates AI warning kill billions</a></div></div>
<div class="result results_links web-result"><div class="result__body">
<a class="result__a" href="https://example.org/unrelated">Cooking pasta</a><a class="result__snippet">recipes</a></div></div>
"""


class RelatedAndTelegram(unittest.TestCase):
    def test_parse_ddg_skips_ads_and_keeps_alignment(self):
        from ainews import search
        r = search.parse_ddg(DDG_HTML)
        self.assertEqual([x["url"] for x in r][:2], ["https://www.reuters.com/tech/gates-ai", "https://techcrunch.com/gates"])
        self.assertEqual(r[0]["title"], "Gates warns AI risks")
        self.assertIn("mass harm", r[0]["snippet"])
        self.assertEqual(r[1]["snippet"], "")          # missing snippet must not borrow the next one
        self.assertFalse(any("y.js" in x["url"] for x in r))

    def test_pick_related_filters_own_site_social_and_irrelevant(self):
        from ainews import search
        res = search.parse_ddg(DDG_HTML)
        got = search.pick_related(res, "Bill Gates AI risk warning", ["https://techcrunch.com/own"], per_item=2)
        urls = [g["url"] for g in got]
        self.assertEqual(urls, ["https://www.reuters.com/tech/gates-ai"])  # techcrunch=own, youtube=social, pasta=irrelevant

    def test_enrich_never_raises(self):
        from ainews import search
        items = [{"title": "T", "sources": [{"url": "https://a.com/x"}]}, {"title": "U", "sources": []}]

        def boom(q):
            raise RuntimeError("captcha")
        search.enrich(items, {}, {"delay_seconds": 0}, search=boom, sleep=lambda s: None)
        self.assertEqual(items[0]["related"], [])
        self.assertEqual(items[0]["search_query"], "T news")

    def test_make_queries(self):
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "k"}), \
                mock.patch.object(llm, "_chat", return_value='ok [{"id":0,"query":"gates ai risk warning"}]'):
            self.assertEqual(llm.make_queries([("t", "s")]), {0: "gates ai risk warning"})
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "k"}), \
                mock.patch.object(llm, "_chat", side_effect=RuntimeError):
            self.assertEqual(llm.make_queries([("t", "s")]), {})

    def test_pipeline_attaches_related_and_telegram_text(self):
        from ainews import notify, search
        cfg = {"window_hours": 36, "max_items": 10, "min_score": 15, "shortlist_size": 30, "dedup_days": 30,
               "sources": [], "search": {"enabled": True, "per_item": 2, "delay_seconds": 0}}
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(search, "search_ddg", lambda q: search.parse_ddg(DDG_HTML)), \
                mock.patch.object(search.time, "sleep", lambda s: None):
            cfg["data_dir"] = d
            out = pipeline.run(cfg, items=fixtures(), now=NOW, dry_run=True)
        gates = next(i for i in out["items"] if "Gates" in i["title"])
        self.assertTrue(gates["related"])
        msg = notify.format_item(1, gates)
        self.assertIn("Related coverage", msg)
        self.assertLessEqual(len(msg), notify.LIMIT)

    def test_format_escapes_html_and_truncates(self):
        from ainews import notify
        it = {"title": "A <b>&</b>", "topic": "other", "score": 50.2, "summary": "x" * 9000,
              "url": "https://a.com/?a=1&b=2", "related": []}
        msg = notify.format_item(1, it)
        self.assertIn("A &lt;b&gt;&amp;&lt;/b&gt;", msg)
        self.assertLessEqual(len(msg), notify.LIMIT)

    def test_send_digest_uses_stringsession_and_swallows_errors(self):
        import sys
        import types
        from ainews import notify
        sent = []

        class Client:
            def __init__(self, session, api_id, api_hash):
                sent.append(("init", session.__class__.__name__ if not isinstance(session, str) else session, api_id))

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def send_message(self, chat, text, parse_mode=None, link_preview=None):
                sent.append((chat, parse_mode, link_preview))
        tl = types.ModuleType("telethon"); tl.TelegramClient = Client
        sess = types.ModuleType("telethon.sessions"); sess.StringSession = lambda s: s
        env = {"TELEGRAM_API_ID": "123", "TELEGRAM_API_HASH": "h", "TELEGRAM_SESSION": "SESS"}
        out = {"items": [{"title": "t", "topic": "other", "score": 1, "summary": "", "url": "https://a.com", "related": []}]}
        with mock.patch.dict(sys.modules, {"telethon": tl, "telethon.sessions": sess}), \
                mock.patch.dict(os.environ, env, clear=True), mock.patch.object(notify.asyncio, "sleep", mock.AsyncMock()):
            self.assertTrue(notify.send_digest(out))
            self.assertEqual(sent, [("init", "SESS", 123), ("me", "html", False)])
            self.assertFalse(notify.send_digest({"items": []}))           # quiet day -> nothing sent
            with mock.patch.object(notify, "_send", side_effect=RuntimeError("net")):
                self.assertFalse(notify.send_digest(out))                 # failure swallowed


if __name__ == "__main__":
    unittest.main()
