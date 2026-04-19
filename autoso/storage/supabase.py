# autoso/storage/supabase.py
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from supabase import create_client, Client

import autoso.config as config
from autoso.scraping.models import Post


CACHE_WINDOW_MINUTES = 30


def _get_client() -> Client:
    return create_client(config.SUPABASE_URL, config.SUPABASE_KEY)


def store_scrape(url: str, post: Post) -> str:
    """Persist a Post as a scrape cache row. Returns the scrape_id (UUID)."""
    client = _get_client()
    scrape_id = str(uuid.uuid4())
    client.table("scrapes").insert(
        {
            "id": scrape_id,
            "url": url,
            "result": post.to_dict(),
        }
    ).execute()
    return scrape_id


def get_recent_scrape(url: str) -> tuple[str, Post] | None:
    """Return most recent scrape for url within cache window."""
    client = _get_client()
    cutoff = (
        datetime.now(timezone.utc) - timedelta(minutes=CACHE_WINDOW_MINUTES)
    ).isoformat()
    resp = (
        client.table("scrapes")
        .select("id, scraped_at, result")
        .eq("url", url)
        .gte("scraped_at", cutoff)
        .order("scraped_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    if not rows:
        return None
    row = rows[0]
    return row["id"], Post.from_dict(row["result"])


def store_result(
    url: str,
    mode: str,
    title: str,
    output: str,
    output_cited: Optional[str],
    citation_index: List[dict],
    scrape_id: str,
) -> str:
    """Persist an analysis result and its citations. Returns the run_id (UUID)."""
    client = _get_client()
    run_id = str(uuid.uuid4())

    client.table("analyses").insert(
        {
            "id": run_id,
            "url": url,
            "mode": mode,
                "title": title,
                "output": output,
                "output_cited": output_cited,
                "scrape_id": scrape_id,
            }
    ).execute()

    if citation_index:
        rows = [
            {
                "run_id": run_id,
                "citation_number": c["citation_number"],
                "text": c["text"],
                "platform": c["platform"],
                "comment_id": c.get("comment_id"),
                "position": c.get("position"),
            }
            for c in citation_index
        ]
        client.table("citations").insert(rows).execute()

    return run_id
