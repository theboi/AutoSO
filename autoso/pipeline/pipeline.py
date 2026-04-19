# autoso/pipeline/pipeline.py
import logging
from dataclasses import dataclass, field
from typing import List, Literal, Optional

from autoso.pipeline.citation import (
    CitationNode,
    build_citation_engine,
    extract_citations,
    strip_citation_markers,
)
from autoso.pipeline.holy_grail import load_holy_grail
from autoso.pipeline.indexer import index_comments
from autoso.pipeline.llm import configure_llm
from autoso.pipeline.prompts import (
    BUCKET_FORMAT_INSTRUCTION,
    BUCKET_SYSTEM_PROMPT,
    TEXTURE_FORMAT_INSTRUCTION,
    TEXTURE_SYSTEM_PROMPT,
)
from autoso.pipeline.title import infer_title
from autoso.scraping import flatten_comments, scrape
from autoso.storage.supabase import store_result

logger = logging.getLogger(__name__)

Mode = Literal["texture", "bucket"]


@dataclass
class PipelineResult:
    title: str
    output: str
    output_cited: str
    citation_index: List[CitationNode] = field(default_factory=list)
    run_id: str = ""


def run_pipeline(
    url: str,
    mode: Mode,
    provided_title: Optional[str] = None,
) -> PipelineResult:
    configure_llm()

    scrape_id, post = scrape(url)
    all_comments = flatten_comments(post)
    logger.info("Scraped %d comments from %s", len(all_comments), post.platform)

    if not all_comments:
        raise RuntimeError(
            f"No comments retrieved from {url}. "
            f"The scraper returned 0 comments — check session cookies, "
            f"proxy, or whether the post has comments."
        )

    title = provided_title or infer_title(post)

    comment_index = index_comments(all_comments)

    comments_text = "\n".join(
        f"Comment {c.position}: {c.text}" for c in all_comments
    )
    post_context = (
        f"{post.platform.upper()} POST:\n{post.content}\n\n"
        f"COMMENTS:\n{comments_text}"
    )

    if mode == "texture":
        system = TEXTURE_SYSTEM_PROMPT
        format_instr = TEXTURE_FORMAT_INSTRUCTION.format(title=title)
        full_query = f"{post_context}\n\n{format_instr}"
    else:
        system = BUCKET_SYSTEM_PROMPT
        holy_grail_index = load_holy_grail()
        hg_engine = build_citation_engine(holy_grail_index, similarity_top_k=20)
        hg_response = hg_engine.query(
            "List all bucket labels for MINDEF/SAF/NS/Defence sentiment analysis"
        )
        format_instr = BUCKET_FORMAT_INSTRUCTION.format(title=title)
        full_query = (
            f"{post_context}\n\n"
            f"BUCKET HOLY GRAIL REFERENCE:\n{hg_response}\n\n"
            f"{format_instr}"
        )

    comment_engine = build_citation_engine(
        comment_index, system_prompt=system
    )

    response = comment_engine.query(full_query)

    output_cited = str(response)
    output_clean = strip_citation_markers(output_cited)

    citations = extract_citations(response)

    run_id = store_result(
        url=url,
        mode=mode,
        title=title,
        output=output_clean,
        output_cited=output_cited,
        citation_index=[
            {
                "citation_number": c.citation_number,
                "text": c.text,
                "platform": c.platform,
                "comment_id": c.id,
                "position": c.position,
            }
            for c in citations
        ],
        scrape_id=scrape_id,
    )

    return PipelineResult(
        title=title,
        output=output_clean,
        output_cited=output_cited,
        citation_index=citations,
        run_id=run_id,
    )
