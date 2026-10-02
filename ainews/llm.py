"""Optional cheap-LLM pass over the shortlist. Defaults to OpenRouter + a very cheap model; any
OpenAI-compatible endpoint works. Only LLM_API_KEY is required; override LLM_BASE_URL / LLM_MODEL to switch."""
import json
import os
import re
from urllib.request import Request, urlopen

PROMPT = """You are a strict editor for a daily AI-industry news digest.
For each candidate decide whether it is a SUBSTANTIVE development (a real launch/release, a credible safety or
policy warning or decision, a notable capability/research result, major funding/regulation, widely discussed
event) versus fluff (a bare CEO/celebrity quote with no new fact, opinion/listicle, rehash, promo).
Return ONLY a JSON array, one object per candidate:
{"id": <int>, "keep": true|false, "topic": "model-release|safety-policy|open-source|funding-business|infra-chips|research|other",
 "impact": <1-10>, "summary": "<=25 words, factual, no hype"}

Candidates:
"""


DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "meta-llama/llama-3.1-8b-instruct"
BATCH = 10  # small batches keep small models' JSON output reliable


def configured():
    return bool(os.environ.get("LLM_API_KEY"))


def _chat(content):
    body = json.dumps({"model": os.environ.get("LLM_MODEL") or DEFAULT_MODEL, "temperature": 0,
                       "messages": [{"role": "user", "content": content}]}).encode()
    base = os.environ.get("LLM_BASE_URL") or DEFAULT_BASE_URL
    req = Request(base.rstrip("/") + "/chat/completions", data=body, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + os.environ["LLM_API_KEY"]})
    with urlopen(req, timeout=120) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def parse_verdicts(raw):
    m = re.search(r"\[.*\]", raw, re.S)
    arr = json.loads(m.group(0) if m else raw)
    return {int(v["id"]): v for v in arr}


def review(stories):
    """Verdicts keyed by index into `stories`. Batches that fail are skipped (those stories keep their
    rule-based score); raises only if every batch failed."""
    verdicts, last_err = {}, None
    for start in range(0, len(stories), BATCH):
        lines = []
        for i, s in enumerate(stories[start:start + BATCH], start):
            top = s.items[0]
            srcs = ", ".join(sorted({it.source for it in s.items})[:5])
            lines.append(f"[{i}] {top.title} | sources: {srcs} | {top.text[:200]}")
        try:
            verdicts.update(parse_verdicts(_chat(PROMPT + "\n".join(lines))))
        except Exception as e:
            last_err = e
    if not verdicts and last_err:
        raise last_err
    return verdicts
