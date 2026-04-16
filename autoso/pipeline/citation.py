# autoso/pipeline/citation.py
import re
from dataclasses import dataclass
from typing import List

from llama_index.core import VectorStoreIndex
from llama_index.core.query_engine import CitationQueryEngine


@dataclass
class CitationNode:
    citation_number: int
    text: str
    platform: str
    comment_id: str
    position: int


def build_citation_engine(
    index: VectorStoreIndex,
    similarity_top_k: int = 10,
    system_prompt: str | None = None,
) -> CitationQueryEngine:
    """Build a CitationQueryEngine that annotates its response with [N] markers."""
    kwargs: dict = {
        "similarity_top_k": similarity_top_k,
        "citation_chunk_size": 512,
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


def extract_citations(response) -> List[CitationNode]:
    """Extract source node metadata from a CitationQueryEngine response."""
    nodes = []
    for i, node in enumerate(response.source_nodes):
        nodes.append(
            CitationNode(
                citation_number=i + 1,
                text=node.node.text,
                platform=node.node.metadata.get("platform", "unknown"),
                comment_id=node.node.metadata.get("comment_id", f"node_{i}"),
                position=node.node.metadata.get("position", -1),
            )
        )
    return nodes


def strip_citation_markers(text: str) -> str:
    """Remove all [N] citation markers from text."""
    return re.sub(r"\s*\[\d+\]", "", text).strip()
