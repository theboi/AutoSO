import logging
from dataclasses import dataclass, field
from typing import Literal, Optional

from autoso.pipeline.analysis import CitationRecord
from autoso.pipeline.citation import build_citation_engine
from autoso.pipeline.flatten import flatten_post_comments
from autoso.pipeline.holy_grail import load_holy_grail
from autoso.pipeline.llm import configure_llm
from autoso.pipeline.pool import build_pool
from autoso.pipeline.prompt_analysis import run_prompt_analysis
from autoso.pipeline.rag_analysis import run_rag_analysis
from autoso.pipeline.scaling import comments_per_link
from autoso.pipeline.title import infer_title
from autoso.scraping import scrape
from autoso.storage.supabase import store_multi_result

logger = logging.getLogger(__name__)

Mode = Literal["texture", "bucket"]
AnalysisMode = Literal["prompt", "rag"]


@dataclass
class PipelineResult:
    title: str
    output: str
    output_cited: str
    citations: list[CitationRecord] = field(default_factory=list)
    run_id: str = ""


def _run_holy_grail() -> str:
    hg_engine = build_citation_engine(load_holy_grail(), similarity_top_k=20)
    response = hg_engine.query(
        "List all bucket labels for MINDEF/SAF/NS/Defence sentiment analysis"
    )
    return str(response)


def run_pipeline(
    urls: list[str],
    mode: Mode,
    analysis_mode: AnalysisMode = "prompt",
    provided_title: Optional[str] = None,
) -> PipelineResult:
    if not urls:
        raise ValueError("urls must be a non-empty list")

    configure_llm()

    scraped = [scrape(url) for url in urls]
    scrape_ids = [scrape_id for scrape_id, _ in scraped]
    posts = [post for _, post in scraped]

    n_cap = comments_per_link(len(urls))
    flattened = [
        flatten_post_comments(post=post, n_cap=n_cap, source_index=source_index)
        for source_index, post in enumerate(posts)
    ]

    logger.info("Scraped %d URLs and flattened %d comments", len(urls), sum(len(f) for f in flattened))

    pool = build_pool(posts=posts, flattened=flattened)
    title = provided_title or infer_title(posts[0])

    hg_block = _run_holy_grail() if mode == "bucket" else None

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
        raise ValueError(f"unknown analysis_mode: {analysis_mode!r}")

    run_id = store_multi_result(
        urls=urls,
        scrape_ids=scrape_ids,
        mode=mode,
        analysis_mode=analysis_mode,
        title=title,
        analysis=analysis,
    )

    return PipelineResult(
        title=title,
        output=analysis.output_clean,
        output_cited=analysis.output_cited,
        citations=analysis.citations,
        run_id=run_id,
    )
