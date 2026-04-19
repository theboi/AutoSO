"""RAG-mode analysis: index the flat pool and use CitationQueryEngine."""
from __future__ import annotations

import uuid
from typing import Optional

import chromadb
from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.vector_stores.chroma import ChromaVectorStore

from autoso.pipeline.analysis import AnalysisResult, CitationRecord
from autoso.pipeline.citation import build_citation_engine, strip_citation_markers
from autoso.pipeline.pool import Pool
from autoso.pipeline.prompt_analysis import render_flat_comment, render_user_message
from autoso.pipeline.prompts import (
    BUCKET_FORMAT_INSTRUCTION,
    BUCKET_SYSTEM_PROMPT,
    TEXTURE_FORMAT_INSTRUCTION,
    TEXTURE_SYSTEM_PROMPT,
)


def _pool_documents(pool: Pool) -> list[Document]:
    docs: list[Document] = []
    for item in pool.items:
        docs.append(
            Document(
                text=render_flat_comment(item),
                metadata={
                    "comment_id": item.flat.original_id,
                    "position": item.flat.position,
                    "source_index": item.flat.source_index,
                    "citation_number": item.citation_number,
                },
                doc_id=f"{item.flat.original_id}:{item.citation_number}",
            )
        )
    return docs


def _index_pool(pool: Pool) -> VectorStoreIndex:
    client = chromadb.EphemeralClient()
    collection = client.create_collection(f"rag_{uuid.uuid4().hex[:12]}")
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage = StorageContext.from_defaults(vector_store=vector_store)
    return VectorStoreIndex.from_documents(
        _pool_documents(pool),
        storage_context=storage,
        show_progress=False,
    )


def _extract_rag_citations(response, pool: Pool) -> list[CitationRecord]:
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


def run_rag_analysis(
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

    index = _index_pool(pool)
    engine = build_citation_engine(
        index,
        similarity_top_k=max(len(pool.items), 1),
        system_prompt=system,
        citation_chunk_size=4096,
    )

    query = render_user_message(
        pool=Pool(items=[], posts=pool.posts),
        format_instruction=format_instruction,
        hg_block=hg_block,
    )

    response = engine.query(query)
    output_cited = str(response)
    output_clean = strip_citation_markers(output_cited)
    citations = _extract_rag_citations(response, pool)
    return AnalysisResult(
        output_cited=output_cited,
        output_clean=output_clean,
        citations=citations,
    )
