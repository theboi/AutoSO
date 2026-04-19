import re

from llama_index.core import VectorStoreIndex
from llama_index.core.query_engine import CitationQueryEngine


def build_citation_engine(
    index: VectorStoreIndex,
    similarity_top_k: int = 10,
    system_prompt: str | None = None,
    citation_chunk_size: int = 512,
) -> CitationQueryEngine:
    """Build a CitationQueryEngine that annotates its response with [N] markers.

    `citation_chunk_size` controls how the engine splits documents into citable
    chunks. For flat-comment indexing (Phase 1Y RAG mode) a large value like
    4096 keeps each comment in a single chunk so citation numbers map 1:1 to
    comments instead of splitting one comment across multiple [N] markers.
    """
    kwargs: dict = {
        "similarity_top_k": similarity_top_k,
        "citation_chunk_size": citation_chunk_size,
    }
    if system_prompt:
        from llama_index.core import PromptTemplate

        qa_template = PromptTemplate(
            "INSTRUCTIONS:\n" + system_prompt + "\n\n"
            "Context information is below.\n"
            "---------------------\n"
            "{context_str}\n"
            "---------------------\n"
            "Given the context information and not prior knowledge, "
            "answer the query.\n"
            "Query: {query_str}\n"
            "Answer: "
        )
        kwargs["text_qa_template"] = qa_template
    return CitationQueryEngine.from_args(index, **kwargs)


def strip_citation_markers(text: str) -> str:
    """Remove all [N] citation markers from text."""
    return re.sub(r"\s*\[\d+\]", "", text).strip()
