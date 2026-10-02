"""Rule-based significance scoring.

Score (0-100) = coverage(30) + community(30) + primary source(15) + category(15) + freshness(10) - penalty.
The idea: rank by how widely and independently something is being discussed, not by who said it.
"""
import math
import re
from datetime import datetime, timezone

AI_RE = re.compile(r"\b(ai|a\.i\.|artificial intelligence|llms?|gpt-?\w*|openai|anthropic|claude|gemini|"
                   r"deepseek|llama|qwen|mistral|grok|copilot|chatbots?|machine learning|neural|nvidia|"
                   r"deepmind|hugging ?face|diffusion|transformers?|agentic|ai agents?|robotics?|openclaw)\b", re.I)

# topic -> (weight 0..15, keywords)
CATEGORIES = {
    "model-release": (15, r"\b(launch(es|ed)?|releas(es|ed)?|introduc(es|ing)|unveil(s|ed)?|announc(es|ed)?|"
                          r"rolls? out|debuts?|open[- ]?weights?|open[- ]?source|v\d+(\.\d+)?|\d+(\.\d+)?b\b)"),
    "safety-policy": (14, r"\b(warn(s|ed|ing)?|risk|existential|danger(ous)?|safety|regulat\w+|law|ban(s|ned)?|"
                          r"lawsuit|sues?|senate|congress|eu ai act|executive order|alignment|extinction)\b"),
    "open-source": (12, r"\b(open[- ]?source|open[- ]?weights?|runs? (locally|on cpu)|cpu[- ]only|on-?device|github)\b"),
    "funding-business": (11, r"\b(raises?|funding|valuation|acquir\w+|acquisition|ipo|billion|invests?|partnership|deal)\b"),
    "infra-chips": (10, r"\b(gpu|chips?|datacenter|data center|tpu|inference|nvidia|compute|supercomputer)\b"),
    "research": (9, r"\b(paper|researchers?|study|benchmark|breakthrough|arxiv|state[- ]of[- ]the[- ]art|sota)\b"),
}
CLICKBAIT_RE = re.compile(r"(\btop \d+\b|\b\d+ (best|ways|things|tools)\b|you won'?t believe|\bhere'?s why\b|"
                          r"\breacts?\b|\bgoes viral\b|\bshocking\b|\bepic\b|\bmust[- ]see\b)", re.I)


def is_ai_relevant(item):
    return bool(AI_RE.search(item.title) or AI_RE.search(item.text[:300]))


def engagement(item):
    m = item.metrics
    # Video views are judged relative to the channel's size so big channels don't dominate.
    video = m.get("views", 0) / m["subs"] * 3000 if m.get("subs") else m.get("views", 0) / 200
    return (m.get("hn_points", 0) + 1.5 * m.get("hn_comments", 0) + 0.5 * m.get("stars", 0)
            + 2 * m.get("likes", 0) + video)


def classify_topic(text):
    best, best_n = "other", 0
    for topic, (_, pat) in CATEGORIES.items():
        n = len(re.findall(pat, text, re.I))
        if n > best_n:
            best, best_n = topic, n
    return best


def _age_hours(iso, now):
    if not iso:
        return 24.0
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return max(0.0, (now - dt).total_seconds() / 3600)


def score_story(story, now=None):
    now = now or datetime.now(timezone.utc)
    items = story.items
    outlets = {it.source for it in items if it.source_type in ("news", "primary", "video")}
    primary = any(it.source_type == "primary" for it in items)
    eng = max(engagement(it) for it in items)
    text = " ".join(it.title for it in items)
    topic = classify_topic(text)
    cat_w = CATEGORIES[topic][0] if topic in CATEGORIES else 0
    newest = min(_age_hours(it.published_at, now) for it in items)
    clickbait = all(CLICKBAIT_RE.search(it.title) for it in items)

    coverage = 30 * min(1.0, max(0, len(outlets) - 1) / 4)
    community = 30 * min(1.0, math.log10(1 + eng) / 3.5)
    prim = 15 if primary else 0
    fresh = 10 * max(0.0, 1 - newest / 72)
    penalty = 20 if clickbait else 0

    story.topic = topic
    story.score = max(0.0, min(100.0, coverage + community + prim + cat_w + fresh - penalty))
    story.signals = {"outlets": len(outlets), "primary_source": primary, "engagement": round(eng),
                     "hn_points": max((it.metrics.get("hn_points", 0) for it in items), default=0),
                     "stars": max((it.metrics.get("stars", 0) for it in items), default=0),
                     "age_hours": round(newest, 1)}
    return story
