"""Optional cheap-LLM pass over the shortlist. Any OpenAI-compatible endpoint works
(DeepSeek, Gemini via OpenAI-compat, Groq, OpenRouter, ...). Configure via env:
LLM_BASE_URL, LLM_MODEL, LLM_API_KEY."""
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


def configured():
    return all(os.environ.get(k) for k in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"))


def _chat(content):
    body = json.dumps({"model": os.environ["LLM_MODEL"], "temperature": 0,
                       "messages": [{"role": "user", "content": content}]}).encode()
    req = Request(os.environ["LLM_BASE_URL"].rstrip("/") + "/chat/completions", data=body, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + os.environ["LLM_API_KEY"]})
    with urlopen(req, timeout=120) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def parse_verdicts(raw):
    m = re.search(r"\[.*\]", raw, re.S)
    arr = json.loads(m.group(0) if m else raw)
    return {int(v["id"]): v for v in arr}


def review(stories):
    lines = []
    for i, s in enumerate(stories):
        top = s.items[0]
        srcs = ", ".join(sorted({it.source for it in s.items})[:5])
        lines.append(f"[{i}] {top.title} | sources: {srcs} | {top.text[:200]}")
    return parse_verdicts(_chat(PROMPT + "\n".join(lines)))
