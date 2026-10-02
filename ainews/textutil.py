import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

_TRACKING = {"fbclid", "gclid", "ref", "ref_src", "source", "mc_cid", "mc_eid", "cmpid", "ocid"}
_STOP = set("""a an the and or of to in on for with at by from is are was were be been it its this that
as but not no new says said say will can could has have had how why what who after before over into
about up out more than just now ai""".split())


def canonical_url(url: str) -> str:
    try:
        p = urlsplit(url.strip())
    except ValueError:
        return url
    host = p.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    q = [(k, v) for k, v in parse_qsl(p.query)
         if not k.lower().startswith("utm_") and k.lower() not in _TRACKING]
    path = p.path.rstrip("/") or "/"
    return urlunsplit((p.scheme.lower() or "https", host, path, urlencode(q), ""))


def domain(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def tokens(title: str) -> frozenset:
    words = re.findall(r"[a-z0-9][a-z0-9.\-]*", title.lower())
    return frozenset(w.strip(".-") for w in words if w not in _STOP and len(w) > 1)


def jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def similar_titles(a: frozenset, b: frozenset, threshold: float) -> bool:
    """Jaccard, or one title almost entirely contained in the other."""
    if jaccard(a, b) >= threshold:
        return True
    small, big = (a, b) if len(a) <= len(b) else (b, a)
    return len(small) >= 4 and len(small & big) / len(small) >= 0.85
