import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autoso.scraping.models import Comment, Post, ScrapeError


_YT_DLP_TIMEOUT = 300


class YouTubeScraper:
    def scrape(self, url: str) -> Post:
        output_dir = tempfile.mkdtemp()
        output_template = str(Path(output_dir) / "%(id)s")

        result = subprocess.run(
            [
                "yt-dlp",
                "--skip-download",
                "--write-info-json",
                "--write-comments",
                "--no-warnings",
                "-o",
                output_template,
                url,
            ],
            capture_output=True,
            text=True,
            timeout=_YT_DLP_TIMEOUT,
        )
        if result.returncode != 0:
            raise ScrapeError(f"yt-dlp failed: {result.stderr.strip()}", cause="unknown")

        info_files = list(Path(output_dir).glob("*.info.json"))
        if not info_files:
            raise ScrapeError(
                f"No .info.json emitted by yt-dlp in {output_dir}",
                cause="selector_drift",
            )
        with open(info_files[0]) as f:
            data = json.load(f)

        return _build_post(url, data)


def _build_post(url: str, data: dict[str, Any]) -> Post:
    comments_flat = data.get("comments") or []
    comments = _nest_comments(comments_flat)

    return Post(
        id=data.get("id", ""),
        platform="youtube",
        url=url,
        page_title=data.get("channel") or "YouTube",
        post_title=data.get("title", ""),
        date=_parse_upload_date(data.get("upload_date")),
        author=data.get("channel"),
        content=data.get("description", ""),
        likes=data.get("like_count"),
        comments=comments,
    )


def _parse_upload_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _nest_comments(raw: list[dict[str, Any]]) -> list[Comment]:
    by_id: dict[str, Comment] = {}
    top_level: list[Comment] = []
    top_pos = 0

    for raw_c in raw:
        c = Comment(
            id=str(raw_c.get("id", "")),
            platform="youtube",
            author=raw_c.get("author"),
            date=_epoch_to_dt(raw_c.get("timestamp")),
            text=raw_c.get("text", ""),
            likes=raw_c.get("like_count"),
            position=0,
        )
        by_id[c.id] = c

    for raw_c in raw:
        cid = str(raw_c.get("id", ""))
        parent = raw_c.get("parent", "root")
        comment = by_id[cid]
        if parent == "root" or parent not in by_id:
            comment.position = top_pos
            top_level.append(comment)
            top_pos += 1
        else:
            by_id[parent].subcomments.append(comment)

    return top_level


def _epoch_to_dt(epoch: float | None) -> datetime | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc)
