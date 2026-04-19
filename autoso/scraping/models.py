from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class ScrapeError(Exception):
    """Base exception for scraping failures with classified cause.

    cause values: "auth_wall" | "proxy" | "selector_drift" | "rate_limit" | "timeout" | "unknown"
    """
    def __init__(self, message: str, cause: str = "unknown"):
        super().__init__(message)
        self.cause = cause


@dataclass
class Comment:
    id: str
    platform: str
    author: str | None
    date: datetime | None
    text: str
    likes: int | None
    position: int
    subcomments: list["Comment"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "platform": self.platform,
            "author": self.author,
            "date": self.date.isoformat() if self.date else None,
            "text": self.text,
            "likes": self.likes,
            "position": self.position,
            "subcomments": [sub.to_dict() for sub in self.subcomments],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Comment":
        return cls(
            id=d["id"],
            platform=d["platform"],
            author=d.get("author"),
            date=datetime.fromisoformat(d["date"]) if d.get("date") else None,
            text=d["text"],
            likes=d.get("likes"),
            position=d["position"],
            subcomments=[cls.from_dict(sub) for sub in d.get("subcomments", [])],
        )


@dataclass
class Post:
    id: str
    platform: str
    url: str
    page_title: str
    post_title: str
    date: datetime | None
    author: str | None
    content: str | None
    likes: int | None
    comments: list[Comment] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "platform": self.platform,
            "url": self.url,
            "page_title": self.page_title,
            "post_title": self.post_title,
            "date": self.date.isoformat() if self.date else None,
            "author": self.author,
            "content": self.content,
            "likes": self.likes,
            "comments": [comment.to_dict() for comment in self.comments],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Post":
        return cls(
            id=d["id"],
            platform=d["platform"],
            url=d["url"],
            page_title=d["page_title"],
            post_title=d["post_title"],
            date=datetime.fromisoformat(d["date"]) if d.get("date") else None,
            author=d.get("author"),
            content=d.get("content"),
            likes=d.get("likes"),
            comments=[Comment.from_dict(comment) for comment in d.get("comments", [])],
        )
