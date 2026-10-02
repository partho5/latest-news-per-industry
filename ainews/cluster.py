from .models import Story
from .textutil import canonical_url, tokens, similar_titles


def cluster(items, threshold=0.5):
    """Union-find: same canonical URL or near-identical title => same story."""
    n = len(items)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    urls = [canonical_url(it.url) for it in items]
    toks = [tokens(it.title) for it in items]
    for i in range(n):
        for j in range(i + 1, n):
            if urls[i] == urls[j] or similar_titles(toks[i], toks[j], threshold):
                parent[find(i)] = find(j)
    groups = {}
    for i, it in enumerate(items):
        groups.setdefault(find(i), []).append(it)
    return [Story(items=g) for g in groups.values()]
