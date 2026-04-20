from unittest.mock import MagicMock, patch

import pytest

from autoso.pipeline.analysis import AnalysisResult, CitationRecord
from autoso.pipeline.pipeline import PipelineResult, run_pipeline
from autoso.scraping.models import Comment, Post


@pytest.fixture
def post() -> Post:
    return Post(
        id="p1",
        platform="reddit",
        url="https://reddit.com/r/test/comments/abc",
        page_title="reddit page",
        post_title="Post title",
        date=None,
        author=None,
        content="The annual exercise has ended.",
        likes=None,
        comments=[
            Comment(
                id="c1",
                platform="reddit",
                author=None,
                date=None,
                text="Strong SAF showing",
                likes=None,
                position=0,
            )
        ],
    )


@pytest.fixture
def analysis_result() -> AnalysisResult:
    return AnalysisResult(
        output_cited="- Point [1]",
        output_clean="- Point",
        citations=[
            CitationRecord(
                citation_number=1,
                text="Strong SAF showing",
                comment_id="c1",
                position=0,
                source_index=0,
            )
        ],
    )


def _default_patches(post: Post, analysis: AnalysisResult):
    pool = MagicMock()
    return {
        "configure_llm": patch("autoso.pipeline.pipeline.configure_llm"),
        "comments_per_link": patch("autoso.pipeline.pipeline.comments_per_link", return_value=500),
        "flatten_post_comments": patch(
            "autoso.pipeline.pipeline.flatten_post_comments", return_value=[]
        ),
        "build_pool": patch("autoso.pipeline.pipeline.build_pool", return_value=pool),
        "run_analysis": patch("autoso.pipeline.pipeline.run_analysis", return_value=analysis),
        "store_multi_result": patch(
            "autoso.pipeline.pipeline.store_multi_result", return_value="run-123"
        ),
        "scrape": patch("autoso.pipeline.pipeline.scrape", return_value=("sid-1", post)),
        "infer_title": patch("autoso.pipeline.pipeline.infer_title", return_value="Inferred Title"),
        "holy_grail": patch("autoso.pipeline.pipeline._run_holy_grail", return_value="HG"),
    }


def test_texture_single_url_returns_result(post, analysis_result):
    p = _default_patches(post, analysis_result)
    with (
        p["configure_llm"],
        p["comments_per_link"],
        p["flatten_post_comments"],
        p["build_pool"],
        p["run_analysis"] as run_analysis,
        p["store_multi_result"],
        p["scrape"],
        p["infer_title"],
        p["holy_grail"],
    ):
        result = run_pipeline(
            urls=["https://reddit.com/r/test/comments/abc"],
            mode="texture",
            provided_title="Custom",
        )

    assert isinstance(result, PipelineResult)
    assert result.title == "Custom"
    assert result.output == "- Point"
    assert result.citations == analysis_result.citations
    run_analysis.assert_called_once()


def test_multi_url_passes_urls_scrape_ids_and_analysis_mode_to_storage(post, analysis_result):
    p = _default_patches(post, analysis_result)
    with (
        p["configure_llm"],
        p["comments_per_link"],
        p["flatten_post_comments"],
        p["build_pool"],
        p["run_analysis"],
        p["store_multi_result"] as store,
        patch(
            "autoso.pipeline.pipeline.scrape",
            side_effect=[("sid-1", post), ("sid-2", post)],
        ),
        p["infer_title"],
        p["holy_grail"],
    ):
        run_pipeline(
            urls=["https://a.com/post", "https://b.com/post"],
            mode="texture",
            provided_title="T",
        )

    _, kwargs = store.call_args
    assert kwargs["urls"] == ["https://a.com/post", "https://b.com/post"]
    assert kwargs["scrape_ids"] == ["sid-1", "sid-2"]
    assert kwargs["analysis_mode"] == "citation"


def test_bucket_uses_holy_grail_and_passes_hg_block(post, analysis_result):
    p = _default_patches(post, analysis_result)
    with (
        p["configure_llm"],
        p["comments_per_link"],
        p["flatten_post_comments"],
        p["build_pool"],
        p["run_analysis"] as run_analysis,
        p["store_multi_result"],
        p["scrape"],
        p["infer_title"],
        p["holy_grail"] as holy,
    ):
        run_pipeline(urls=["https://a.com/post"], mode="bucket")

    holy.assert_called_once()
    assert run_analysis.call_args.kwargs["hg_block"] == "HG"


def test_texture_skips_holy_grail(post, analysis_result):
    p = _default_patches(post, analysis_result)
    with (
        p["configure_llm"],
        p["comments_per_link"],
        p["flatten_post_comments"],
        p["build_pool"],
        p["run_analysis"] as run_analysis,
        p["store_multi_result"],
        p["scrape"],
        p["infer_title"],
        p["holy_grail"] as holy,
    ):
        run_pipeline(urls=["https://a.com/post"], mode="texture")

    holy.assert_not_called()
    assert run_analysis.call_args.kwargs["hg_block"] is None


def test_empty_urls_raises_value_error():
    with pytest.raises(ValueError, match="non-empty"):
        run_pipeline(urls=[], mode="texture")


def test_infer_title_used_when_no_title(post, analysis_result):
    p = _default_patches(post, analysis_result)
    with (
        p["configure_llm"],
        p["comments_per_link"],
        p["flatten_post_comments"],
        p["build_pool"],
        p["run_analysis"],
        p["store_multi_result"],
        p["scrape"],
        p["infer_title"] as infer,
        p["holy_grail"],
    ):
        result = run_pipeline(
            urls=["https://a.com/post"],
            mode="texture",
            provided_title=None,
        )

    infer.assert_called_once_with(post)
    assert result.title == "Inferred Title"
