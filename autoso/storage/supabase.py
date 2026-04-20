import uuid
from datetime import datetime, timedelta, timezone

from supabase import Client, create_client

import autoso.config as config
from autoso.pipeline.analysis import AnalysisResult
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


def store_multi_result(
    urls: list[str],
    scrape_ids: list[str],
    mode: str,
    title: str,
    analysis: AnalysisResult,
) -> str:
    """Insert analysis + sources + citations. Returns run_id."""
    if len(urls) != len(scrape_ids):
        raise ValueError("urls and scrape_ids must be the same length")

    client = _get_client()
    run_id = str(uuid.uuid4())

    client.table("analyses").insert(
        {
            "id": run_id,
            "mode": mode,
            "title": title,
            "output": analysis.output_clean,
            "output_cited": analysis.output_cited,
        }
    ).execute()

    source_rows = [
        {
            "analysis_id": run_id,
            "url": url,
            "link_index": i,
            "scrape_id": scrape_ids[i],
        }
        for i, url in enumerate(urls)
    ]
    sources_resp = client.table("analysis_sources").insert(source_rows).execute()
    source_rows_returned = sources_resp.data or []
    source_id_by_index: dict[int, str] = {
        row["link_index"]: row["id"] for row in source_rows_returned
    }

    if analysis.citations:
        citation_rows = [
            {
                "run_id": run_id,
                "source_id": source_id_by_index[c.source_index],
                "citation_number": c.citation_number,
                "text": c.text,
                "comment_id": c.comment_id,
                "position": c.position,
            }
            for c in analysis.citations
        ]
        client.table("citations").insert(citation_rows).execute()

    return run_id
