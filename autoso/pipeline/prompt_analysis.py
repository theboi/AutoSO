"""Prompt-mode analysis: direct Anthropic SDK with all comments inline."""

from __future__ import annotations

import re
from typing import Optional

import anthropic

import autoso.config as config
from autoso.pipeline.analysis import AnalysisResult, CitationRecord
from autoso.pipeline.citation import strip_citation_markers
from autoso.pipeline.pool import Pool, PoolItem
from autoso.pipeline.prompts import (
    BUCKET_FORMAT_INSTRUCTION,
    BUCKET_SYSTEM_PROMPT,
    TEXTURE_FORMAT_INSTRUCTION,
    TEXTURE_SYSTEM_PROMPT,
)

_APPEND_INSTRUCTION = (
    "After each bullet point or numbered item, append the citation markers [N] for the "
    "comments that support it. ALWAYS use square brackets, e.g. [65] [105] [132]. "
    "NEVER write bare numbers without brackets. Use the bracketed numbers shown in the "
    "COMMENTS block above."
)

_MARKER_RE = re.compile(r"\[(\d+)\]")


def render_flat_comment(item: PoolItem) -> str:
    """Render a single PoolItem for the prompt's COMMENTS block."""
    n = item.citation_number
    flat = item.flat
    if not flat.thread_context:
        return f"[{n}] {flat.text}"

    lines = [f"[{n}] ↳ reply in thread:"]
    lines.append(f"  parent: {flat.thread_context[0]}")
    for prior in flat.thread_context[1:]:
        lines.append(f"  · {prior}")
    lines.append(flat.text)
    return "\n".join(lines)


def render_user_message(
    pool: Pool, format_instruction: str, hg_block: Optional[str] = None
) -> str:
    """Assemble the single user-turn message for the Anthropic call."""
    parts: list[str] = []
    parts.append(f"POSTS ({len(pool.posts)} sources):")
    for i, post in enumerate(pool.posts, start=1):
        parts.append(f"\n[Source {i} — {post.platform.upper()}] {post.url}\n{post.content or ''}")

    if hg_block:
        parts.append(f"\nBUCKET HOLY GRAIL REFERENCE:\n{hg_block}")

    parts.append("\nCOMMENTS:")
    for item in pool.items:
        parts.append(render_flat_comment(item))

    parts.append("")
    parts.append(format_instruction)
    parts.append("")
    parts.append(_APPEND_INSTRUCTION)
    return "\n".join(parts)


def extract_citations_from_output(output_text: str, pool: Pool) -> list[CitationRecord]:
    """Pull [N] markers from model output and map to CitationRecords via the pool."""
    seen: set[int] = set()
    records: list[CitationRecord] = []

    for match in _MARKER_RE.finditer(output_text):
        citation_number = int(match.group(1))
        if citation_number in seen:
            continue
        seen.add(citation_number)

        item = pool.lookup(citation_number)
        if item is None:
            continue

        flat = item.flat
        records.append(
            CitationRecord(
                citation_number=citation_number,
                text=flat.text,
                comment_id=flat.original_id,
                position=flat.position,
                source_index=flat.source_index,
            )
        )

    return records


def run_prompt_analysis(
    mode: str,
    title: str,
    pool: Pool,
    hg_block: Optional[str],
) -> AnalysisResult:
    if getattr(config, "USE_OLLAMA", False):
        raise RuntimeError(
            "prompt mode requires Anthropic API; set USE_OLLAMA=false or use -m rag"
        )

    if mode == "texture":
        system = TEXTURE_SYSTEM_PROMPT
        format_instruction = TEXTURE_FORMAT_INSTRUCTION.format(title=title)
    elif mode == "bucket":
        system = BUCKET_SYSTEM_PROMPT
        format_instruction = BUCKET_FORMAT_INSTRUCTION.format(title=title)
    else:
        raise ValueError(f"unknown mode: {mode!r}")

    user_message = render_user_message(
        pool=pool,
        format_instruction=format_instruction,
        hg_block=hg_block,
    )

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )

    output_cited = "".join(getattr(block, "text", "") for block in response.content)
    output_clean = strip_citation_markers(output_cited)
    citations = extract_citations_from_output(output_cited, pool)
    return AnalysisResult(
        output_cited=output_cited,
        output_clean=output_clean,
        citations=citations,
    )
