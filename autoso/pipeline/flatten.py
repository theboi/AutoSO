"""Flatten a Post's comments into FlatComment records for analysis."""

from __future__ import annotations

from dataclasses import dataclass, field

from autoso.scraping.models import Post

MAX_THREAD_MESSAGES = 10


@dataclass
class FlatComment:
    original_id: str
    position: int
    text: str
    thread_context: list[str] = field(default_factory=list)
    source_index: int = 0


def flatten_post_comments(post: Post, n_cap: int, source_index: int) -> list[FlatComment]:
    out: list[FlatComment] = []
    if not post.comments or n_cap <= 0:
        return out

    for top in post.comments:
        if len(out) >= n_cap:
            break

        out.append(
            FlatComment(
                original_id=top.id,
                position=len(out),
                text=top.text,
                thread_context=[],
                source_index=source_index,
            )
        )

        running_context: list[str] = [top.text]
        for reply in top.subcomments[: MAX_THREAD_MESSAGES - 1]:
            if len(out) >= n_cap:
                break

            out.append(
                FlatComment(
                    original_id=reply.id,
                    position=len(out),
                    text=reply.text,
                    thread_context=list(running_context),
                    source_index=source_index,
                )
            )
            running_context.append(reply.text)

    return out
