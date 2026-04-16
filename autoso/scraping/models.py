from dataclasses import dataclass, field
from typing import List


class ScrapeError(Exception):
    """Base exception for scraping failures with classified cause.

    cause values: "auth_wall" | "proxy" | "selector_drift" | "rate_limit" | "timeout" | "unknown"
    """
    def __init__(self, message: str, cause: str = "unknown"):
        super().__init__(message)
        self.cause = cause


@dataclass
class Comment:
    platform: str      # "reddit" | "instagram" | "facebook"
    text: str
    comment_id: str    # platform-specific ID or synthetic (e.g. "ig_42")
    position: int      # 0-indexed order in the comment list


@dataclass
class Post:
    title: str
    content: str       # post body text
    url: str
    platform: str
    comments: List[Comment] = field(default_factory=list)
