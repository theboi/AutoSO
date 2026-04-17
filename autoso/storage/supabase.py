# autoso/storage/supabase.py
import uuid
from typing import List, Optional

from supabase import create_client, Client

import autoso.config as config


def _get_client() -> Client:
    return create_client(config.SUPABASE_URL, config.SUPABASE_KEY)


def store_result(
    url: str,
    mode: str,
    title: str,
    output: str,
    output_cited: Optional[str],
    citation_index: List[dict],
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
