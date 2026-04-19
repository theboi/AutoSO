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


def run(
    post: Post,
    mode: Literal["texture", "bucket"],
    analysis_mode: Literal["prompt", "rag"] = "prompt",
) -> dict:
    """Run LLM analysis on post and return a result dict.

    Returns:
        {"ok": True, "mode": ..., "title": ..., "output": ..., "citation_count": N}
        {"ok": True, "mode": ..., "skipped": True, "reason": "..."}  # bucket without holy grail
        {"ok": False, "mode": ..., "error": "..."}
    """
    from autoso.pipeline.flatten import flatten_post_comments
    from autoso.pipeline.llm import configure_llm
    from autoso.pipeline.pool import build_pool
    from autoso.pipeline.prompt_analysis import run_prompt_analysis
    from autoso.pipeline.rag_analysis import run_rag_analysis

    try:
        if mode not in {"texture", "bucket"}:
            return {"ok": False, "mode": mode, "error": f"unknown mode: {mode!r}"}

        configure_llm()

        title = post.post_title
        flattened = [flatten_post_comments(post=post, n_cap=500, source_index=0)]
        pool = build_pool(posts=[post], flattened=flattened)

        hg_block = None
        if mode == "bucket":
            try:
                from autoso.pipeline.pipeline import _run_holy_grail

                hg_block = _run_holy_grail()
            except RuntimeError:
                return {
                    "ok": True,
                    "mode": mode,
                    "skipped": True,
                    "reason": "Holy Grail not ingested — run: python scripts/ingest_holy_grail.py <path>",
                }

        if analysis_mode == "prompt":
            analysis = run_prompt_analysis(
                mode=mode,
                title=title,
                pool=pool,
                hg_block=hg_block,
            )
        elif analysis_mode == "rag":
            analysis = run_rag_analysis(
                mode=mode,
                title=title,
                pool=pool,
                hg_block=hg_block,
            )
        else:
            return {
                "ok": False,
                "mode": mode,
                "error": f"unknown analysis_mode: {analysis_mode!r}",
            }

        return {
            "ok": True,
            "mode": mode,
            "title": title,
            "output": analysis.output_clean,
            "citation_count": len(analysis.citations),
        }

    except Exception as exc:
        return {"ok": False, "mode": mode, "error": str(exc)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live LLM analysis diagnostic")
    parser.add_argument("--mode", choices=["texture", "bucket"], default="texture")
    parser.add_argument("--analysis-mode", choices=["prompt", "rag"], default="prompt")
    args = parser.parse_args()

    result = run(_CLI_CANNED_POST, args.mode, analysis_mode=args.analysis_mode)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)
