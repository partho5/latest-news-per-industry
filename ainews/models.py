from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Item:
    """One raw candidate from a single source."""
    title: str
    url: str
    source: str                      # human name, e.g. "TechCrunch"
    source_type: str                 # primary | news | community | video
    published_at: Optional[str] = None   # ISO-8601 UTC
    text: str = ""
    metrics: dict = field(default_factory=dict)  # hn_points, hn_comments, stars, likes, views


@dataclass
class Story:
    """Items about the same event, merged."""
    items: list
    score: float = 0.0
    topic: str = "other"
    summary: str = ""
    signals: dict = field(default_factory=dict)
