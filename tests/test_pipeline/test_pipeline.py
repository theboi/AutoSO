import re
from unittest.mock import MagicMock, patch

from autoso.pipeline.pipeline import PipelineResult, run_pipeline
from autoso.scraping.models import Comment, Post


def _make_post(platform: str = "reddit") -> Post:
    return Post(
        id="p1",
        platform=platform,
        url=f"https://{platform}.com/test",
        page_title=f"{platform} page",
        post_title="XLS25 Concludes",
        date=None,
        author=None,
        content="The annual exercise has ended.",
        likes=None,
        comments=[
            Comment(
                id="c1",
                platform=platform,
                author=None,
                date=None,
                text="SAF soldiers were impressive",
                likes=None,
                position=0,
            ),
            Comment(
                id="c2",
                platform=platform,
                author=None,
                date=None,
                text="Good for SG-US bilateral relations",
                likes=None,
                position=1,
            ),
            Comment(
                id="c3",
                platform=platform,
                author=None,
                date=None,
                text="NS builds character and resilience",
                likes=None,
                position=2,
            ),
        ],
    )


def _patch_pipeline(mode: str, post: Post, run_id: str = "run-123"):
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
        patch("autoso.pipeline.pipeline.scrape", return_value=("sid-1", post)),
        patch("autoso.pipeline.pipeline.configure_llm"),
        patch("autoso.pipeline.pipeline.store_result", return_value=run_id),
        patch("autoso.pipeline.pipeline.build_citation_engine", return_value=mock_engine),
        patch("autoso.pipeline.pipeline.index_comments", return_value=MagicMock()),
    ]
    if mode == "bucket":
        patches.append(
            patch("autoso.pipeline.pipeline.load_holy_grail", return_value=MagicMock())
        )

    return patches


def test_texture_returns_pipeline_result():
    post = _make_post()
    patches = _patch_pipeline("texture", post)
    started = [p.start() for p in patches]
    try:
        result = run_pipeline(
            url="https://reddit.com/r/test/comments/abc",
            mode="texture",
            provided_title="XLS25 Concludes",
        )
        assert isinstance(result, PipelineResult)
        assert result.title == "XLS25 Concludes"
        assert result.run_id == "run-123"
        assert not re.search(r"\[\d+\]", result.output)
        _, kwargs = started[2].call_args
        assert kwargs["scrape_id"] == "sid-1"
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
    extra_patch = patch("autoso.pipeline.pipeline.infer_title", return_value="Inferred Title")
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


@patch("autoso.pipeline.pipeline.scrape")
@patch("autoso.pipeline.pipeline.configure_llm")
@patch("autoso.pipeline.pipeline.store_result", return_value="run-123")
@patch("autoso.pipeline.pipeline.build_citation_engine")
@patch("autoso.pipeline.pipeline.index_comments", return_value=MagicMock())
def test_pipeline_passes_scrape_id_to_store_result(
    mock_index,
    mock_build_engine,
    mock_store_result,
    mock_configure,
    mock_scrape,
):
    post = _make_post()
    mock_scrape.return_value = ("sid-1", post)

    mock_response = MagicMock()
    mock_response.__str__ = lambda self: "output [1]"
    mock_response.source_nodes = []
    mock_engine = MagicMock()
    mock_engine.query.return_value = mock_response
    mock_build_engine.return_value = mock_engine

    run_pipeline(
        url="https://reddit.com/r/test",
        mode="texture",
        provided_title="T",
    )

    _, kwargs = mock_store_result.call_args
    assert kwargs["scrape_id"] == "sid-1"
