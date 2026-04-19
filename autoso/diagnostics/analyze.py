# autoso/diagnostics/analyze.py
"""Verify that the LLM analysis pipeline produces valid texture/bucket output.

Usage:
    python -m autoso.diagnostics.analyze --mode texture
    python -m autoso.diagnostics.analyze --mode bucket
"""
import argparse
import json
import sys
from typing import Literal

from autoso.scraping import flatten_comments
from autoso.scraping.models import Comment, Post

# Inline canned post for CLI use (tests use the richer one from tests/integration/data.py)
_CLI_CANNED_POST = Post(
    id="diag_post",
    platform="reddit",
    url="https://www.reddit.com/r/singapore/comments/cli_test",
    page_title="r/singapore",
    post_title="Singapore NS Policy Discussion",
    date=None,
    author=None,
    content="Singapore introduces new National Service policy changes for 2024.",
    likes=None,
    comments=[
        Comment(id="c1", platform="reddit", author=None, date=None, text="NS has been very beneficial for Singapore's defence.", likes=None, position=0),
        Comment(id="c2", platform="reddit", author=None, date=None, text="The training builds character and discipline in young men.", likes=None, position=1),
        Comment(id="c3", platform="reddit", author=None, date=None, text="MINDEF should improve NSF allowances — the pay is too low.", likes=None, position=2),
        Comment(id="c4", platform="reddit", author=None, date=None, text="NS is a necessary sacrifice for the country's security.", likes=None, position=3),
        Comment(id="c5", platform="reddit", author=None, date=None, text="The new policy changes modernise our defence force.", likes=None, position=4),
        Comment(id="c6", platform="reddit", author=None, date=None, text="Management quality varies a lot across different units.", likes=None, position=5),
        Comment(id="c7", platform="reddit", author=None, date=None, text="NS teaches time management and teamwork.", likes=None, position=6),
        Comment(id="c8", platform="reddit", author=None, date=None, text="Consider the opportunity cost of 2 years for young Singaporeans.", likes=None, position=7),
    ],
)


def run(post: Post, mode: Literal["texture", "bucket"]) -> dict:
    """Run LLM analysis on post and return a result dict.

    Skips (ok=True, skipped=True) for bucket mode if Holy Grail is not ingested.

    Returns:
        {"ok": True, "mode": ..., "title": ..., "output": ..., "citation_count": N}
        {"ok": True, "skipped": True, "reason": "..."}   # bucket without holy grail
        {"ok": False, "mode": ..., "error": "..."}
    """
    from autoso.pipeline.citation import build_citation_engine, extract_citations, strip_citation_markers
    from autoso.pipeline.indexer import index_comments
    from autoso.pipeline.llm import configure_llm
    from autoso.pipeline.prompts import (
        BUCKET_FORMAT_INSTRUCTION,
        BUCKET_SYSTEM_PROMPT,
        TEXTURE_FORMAT_INSTRUCTION,
        TEXTURE_SYSTEM_PROMPT,
    )

    try:
        configure_llm()
        all_comments = flatten_comments(post)
        comment_index = index_comments(all_comments)

        comments_text = "\n".join(f"Comment {c.position}: {c.text}" for c in all_comments)
        post_context = (
            f"{post.platform.upper()} POST:\n{post.content}\n\n"
            f"COMMENTS:\n{comments_text}"
        )

        if mode == "texture":
            system = TEXTURE_SYSTEM_PROMPT
            full_query = f"{post_context}\n\n{TEXTURE_FORMAT_INSTRUCTION.format(title=post.post_title)}"

        elif mode == "bucket":
            from autoso.pipeline.holy_grail import load_holy_grail
            try:
                holy_grail_index = load_holy_grail()
            except RuntimeError:
                return {
                    "ok": True,
                    "skipped": True,
                    "reason": "Holy Grail not ingested — run: python scripts/ingest_holy_grail.py <path>",
                }
            system = BUCKET_SYSTEM_PROMPT
            hg_engine = build_citation_engine(holy_grail_index, similarity_top_k=20)
            hg_response = hg_engine.query(
                "List all bucket labels for MINDEF/SAF/NS/Defence sentiment analysis"
            )
            full_query = (
                f"{post_context}\n\n"
                f"BUCKET HOLY GRAIL REFERENCE:\n{hg_response}\n\n"
                f"{BUCKET_FORMAT_INSTRUCTION.format(title=post.post_title)}"
            )
        else:
            return {"ok": False, "mode": mode, "error": f"unknown mode: {mode!r}"}

        engine = build_citation_engine(comment_index, system_prompt=system)
        response = engine.query(full_query)
        output_cited = str(response)
        output_clean = strip_citation_markers(output_cited)
        citations = extract_citations(response)

        return {
            "ok": True,
            "mode": mode,
            "title": post.post_title,
            "output": output_clean,
            "citation_count": len(citations),
        }

    except Exception as exc:
        return {"ok": False, "mode": mode, "error": str(exc)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live LLM analysis diagnostic")
    parser.add_argument("--mode", choices=["texture", "bucket"], default="texture")
    args = parser.parse_args()

    result = run(_CLI_CANNED_POST, args.mode)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)
