# tests/test_pipeline/test_pipeline.py
import re
from dataclasses import dataclass
from unittest.mock import MagicMock, patch
from autoso.scraping.models import Comment, Post
from autoso.pipeline.pipeline import run_pipeline, PipelineResult


def _make_post(platform: str = "reddit") -> Post:
    return Post(
        title="XLS25 Concludes",
        content="The annual exercise has ended.",
        url=f"https://{platform}.com/test",
        platform=platform,
        comments=[
            Comment(platform=platform, text="SAF soldiers were impressive", comment_id="c1", position=0),
            Comment(platform=platform, text="Good for SG-US bilateral relations", comment_id="c2", position=1),
            Comment(platform=platform, text="NS builds character and resilience", comment_id="c3", position=2),
        ],
    )


def _patch_pipeline(mode: str, post: Post, run_id: str = "run-123"):
    mock_scraper = MagicMock()
    mock_scraper.scrape.return_value = post

    mock_response = MagicMock()
    mock_response.__str__ = lambda self: (
        "- 60% praised SAF [1]\n- 40% discussed NS [2]"
        if mode == "texture"
        else "*Positive*\n1.  Praised SAF capability [1]\n\n*Neutral*\n1.  Discussed NS [2]\n\n*Negative*\n1.  Criticised budget [3]"
    )
    mock_response.source_nodes = []

    mock_engine = MagicMock()
    mock_engine.query.return_value = mock_response

    patches = [
        patch("autoso.pipeline.pipeline.get_scraper", return_value=mock_scraper),
        patch("autoso.pipeline.pipeline.configure_llm"),
        patch("autoso.pipeline.pipeline.store_result", return_value=run_id),
        patch("autoso.pipeline.pipeline.build_citation_engine", return_value=mock_engine),
        patch("autoso.pipeline.pipeline.index_comments", return_value=MagicMock()),
    ]
    if mode == "bucket":
        patches.append(patch("autoso.pipeline.pipeline.load_holy_grail", return_value=MagicMock()))

    return patches


def test_texture_returns_pipeline_result():
    post = _make_post()
    patches = _patch_pipeline("texture", post)
    mocks = [p.start() for p in patches]
    try:
        result = run_pipeline(
            url="https://reddit.com/r/test/comments/abc",
            mode="texture",
            provided_title="XLS25 Concludes",
        )
        assert isinstance(result, PipelineResult)
        assert result.title == "XLS25 Concludes"
        assert result.run_id == "run-123"
        assert not re.search(r'\[\d+\]', result.output)
    finally:
        for p in patches:
            p.stop()


def test_bucket_loads_holy_grail():
    post = _make_post()
    patches = _patch_pipeline("bucket", post)
    extra_patch = patch("autoso.pipeline.pipeline.infer_title", return_value="Bucket Title")
    [p.start() for p in patches]
    extra_patch.start()
    try:
        run_pipeline(url="https://reddit.com/r/test/comments/abc", mode="bucket")
    finally:
        for p in patches:
            p.stop()
        extra_patch.stop()


def test_texture_uses_provided_title():
    post = _make_post()
    patches = _patch_pipeline("texture", post)
    [p.start() for p in patches]
    try:
        result = run_pipeline(
            url="https://reddit.com/r/test",
            mode="texture",
            provided_title="My Custom Title",
        )
        assert result.title == "My Custom Title"
    finally:
        for p in patches:
            p.stop()


def test_texture_infers_title_when_not_provided():
    post = _make_post()
    patches = _patch_pipeline("texture", post)
    extra_patch = patch(
        "autoso.pipeline.pipeline.infer_title", return_value="Inferred Title"
    )
    [p.start() for p in patches]
    extra_patch.start()
    try:
        result = run_pipeline(
            url="https://reddit.com/r/test",
            mode="texture",
            provided_title=None,
        )
        assert result.title == "Inferred Title"
    finally:
        for p in patches:
            p.stop()
        extra_patch.stop()
