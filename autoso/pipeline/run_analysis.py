"""Unified analysis: SummaryIndex + CitationQueryEngine (no vector search on comments)."""

from __future__ import annotations

from typing import Optional

from llama_index.core import SummaryIndex
from llama_index.core.schema import TextNode

from autoso.pipeline.analysis import AnalysisResult, CitationRecord
from autoso.pipeline.citation import build_citation_engine, strip_citation_markers
from autoso.pipeline.pool import Pool, PoolItem
from autoso.pipeline.prompt_analysis import render_user_message
from autoso.pipeline.prompts import (
    BUCKET_FORMAT_INSTRUCTION,
    BUCKET_SYSTEM_PROMPT,
    TEXTURE_FORMAT_INSTRUCTION,
    TEXTURE_SYSTEM_PROMPT,
)


def _render_node_text(item: PoolItem) -> str:
    flat = item.flat
    if not flat.thread_context:
        return flat.text
    lines = ["↳ reply in thread:"]
    lines.append(f"  parent: {flat.thread_context[0]}")
    for prior in flat.thread_context[1:]:
        lines.append(f"  · {prior}")
    lines.append(flat.text)
    return "\n".join(lines)


def _extract_citations(response, pool: Pool) -> list[CitationRecord]:
    seen: set[tuple[str, int]] = set()
    records: list[CitationRecord] = []
    for node in response.source_nodes:
        meta = node.node.metadata
        comment_id = meta.get("comment_id")
        source_index = meta.get("source_index", 0)
        key = (comment_id, source_index)
        if key in seen:
            continue
        seen.add(key)

        citation_number = meta.get("citation_number")
        item = pool.lookup(citation_number) if citation_number else None
        text = item.flat.text if item else node.node.text
        position = item.flat.position if item else meta.get("position", -1)
        records.append(
            CitationRecord(
                citation_number=citation_number,
                text=text,
                comment_id=comment_id,
                position=position,
                source_index=source_index,
            )
        )
    return records


def run_analysis(
    mode: str,
    title: str,
    pool: Pool,
    hg_block: Optional[str],
) -> AnalysisResult:
    if mode == "texture":
        system = TEXTURE_SYSTEM_PROMPT
        format_instruction = TEXTURE_FORMAT_INSTRUCTION.format(title=title)
    elif mode == "bucket":
        system = BUCKET_SYSTEM_PROMPT
        format_instruction = BUCKET_FORMAT_INSTRUCTION.format(title=title)
    else:
        raise ValueError(f"unknown mode: {mode!r}")

    nodes = [
        TextNode(
            text=_render_node_text(item),
            id_=f"comment_{item.citation_number}",
            metadata={
                "comment_id": item.flat.original_id,
                "position": item.flat.position,
                "source_index": item.flat.source_index,
                "citation_number": item.citation_number,
            },
        )
        for item in pool.items
    ]

    index = SummaryIndex(nodes)
    engine = build_citation_engine(
        index,
        similarity_top_k=max(len(nodes), 1),
        system_prompt=system,
        citation_chunk_size=2048,
    )

    query = render_user_message(
        pool=Pool(items=[], posts=pool.posts),
        format_instruction=format_instruction,
        hg_block=hg_block,
    )

    response = engine.query(query)
    output_cited = str(response)
    output_clean = strip_citation_markers(output_cited)
    citations = _extract_citations(response, pool)
    return AnalysisResult(
        output_cited=output_cited,
        output_clean=output_clean,
        citations=citations,
    )
