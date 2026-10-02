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


if __name__ == "__main__":
    unittest.main()
