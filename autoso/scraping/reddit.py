from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from autoso.scraping.models import Comment, Post, ScrapeError


_USER_AGENT = "AutoSO/1.0 (scraping)"
_TIMEOUT = 20.0


class RedditScraper:
    def scrape(self, url: str) -> Post:
        json_url = url.rstrip("/") + ".json"
        try:
            resp = httpx.get(
                json_url,
                headers={"User-Agent": _USER_AGENT},
                follow_redirects=True,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            payload = resp.json()
        except httpx.TimeoutException as exc:
            raise ScrapeError(f"Reddit JSON fetch timed out: {exc}", cause="timeout")
        except httpx.HTTPStatusError as exc:
            cause = "rate_limit" if exc.response.status_code == 429 else "unknown"
            raise ScrapeError(f"Reddit JSON HTTP error: {exc}", cause=cause)
        except Exception as exc:
            raise ScrapeError(f"Reddit JSON fetch failed: {exc}", cause="unknown")

        if not isinstance(payload, list) or len(payload) < 2:
            raise ScrapeError("Unexpected Reddit JSON shape", cause="selector_drift")

        post_listing, comment_listing = payload[0], payload[1]
        post_children = post_listing.get("data", {}).get("children", [])
        if not post_children:
            raise ScrapeError("Reddit post listing empty", cause="selector_drift")

        post_data = post_children[0].get("data", {})
        comment_children = comment_listing.get("data", {}).get("children", [])

        comments = _build_comments(comment_children)

        return Post(
            id=post_data.get("id", ""),
            platform="reddit",
            url=url,
            page_title=post_data.get("subreddit_name_prefixed", "") or "reddit",
            post_title=post_data.get("title", ""),
            date=_epoch_to_datetime(post_data.get("created_utc")),
            author=post_data.get("author"),
            content=post_data.get("selftext") or post_data.get("title", ""),
            likes=post_data.get("score"),
            comments=comments,
        )


def _epoch_to_datetime(epoch: float | None) -> datetime | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc)


def _is_deleted(body: str | None, author: str | None) -> bool:
    if body is None:
        return True
    stripped = body.strip()
    return stripped in ("[deleted]", "[removed]")


def _build_comments(children: list[dict[str, Any]]) -> list[Comment]:
    comments: list[Comment] = []
    position = 0
    for child in children:
        if child.get("kind") != "t1":
            continue
        data = child.get("data", {})
        if _is_deleted(data.get("body"), data.get("author")):
            continue
        comment = _child_to_comment(data, position)
        comments.append(comment)
        position += 1
    return comments


def _child_to_comment(data: dict[str, Any], position: int) -> Comment:
    subcomments: list[Comment] = []
    replies = data.get("replies")
    if isinstance(replies, dict):
        reply_children = replies.get("data", {}).get("children", [])
        sub_position = 0
        for rc in reply_children:
            if rc.get("kind") != "t1":
                continue
            rdata = rc.get("data", {})
            if _is_deleted(rdata.get("body"), rdata.get("author")):
                continue
            subcomments.append(_child_to_comment(rdata, sub_position))
            sub_position += 1

    return Comment(
        id=data.get("id", ""),
        platform="reddit",
        author=data.get("author"),
        date=_epoch_to_datetime(data.get("created_utc")),
        text=data.get("body", ""),
        likes=data.get("score"),
        position=position,
        subcomments=subcomments,
    )
