from unittest.mock import MagicMock, patch

from autoso.pipeline.analysis import AnalysisResult, CitationRecord
from autoso.pipeline.flatten import FlatComment
from autoso.pipeline.pool import Pool, PoolItem
from autoso.pipeline.prompt_analysis import (
    extract_citations_from_output,
    render_flat_comment,
    render_user_message,
    run_prompt_analysis,
)
from autoso.scraping.models import Post


def _post(url: str, platform: str = "facebook", content: str = "the post body") -> Post:
    return Post(
        id=url,
        platform=platform,
        url=url,
        page_title="",
        post_title="",
        date=None,
        author=None,
        content=content,
        likes=None,
        comments=[],
    )


def _pool_with_two_items() -> Pool:
    return Pool(
        items=[
            PoolItem(1, FlatComment("a1", 0, "alpha", [], 0)),
            PoolItem(2, FlatComment("b1", 0, "bravo", [], 1)),
        ],
        posts=[_post("https://a.com"), _post("https://b.com")],
    )


def _texture_pool() -> Pool:
    return Pool(
        items=[
            PoolItem(1, FlatComment("a1", 0, "alpha", [], 0)),
            PoolItem(2, FlatComment("b1", 0, "bravo", [], 0)),
        ],
        posts=[_post("https://a.com")],
    )


def test_render_flat_comment_top_level():
    item = PoolItem(
        citation_number=5,
        flat=FlatComment(
            original_id="c1",
            position=0,
            text="alpha",
            thread_context=[],
            source_index=0,
        ),
    )

    rendered = render_flat_comment(item)

    assert rendered == "[5] alpha"


def test_render_flat_comment_reply_includes_thread():
    item = PoolItem(
        citation_number=12,
        flat=FlatComment(
            original_id="r1",
            position=4,
            text="disagreed",
            thread_context=["parent says", "first reply"],
            source_index=1,
        ),
    )

    rendered = render_flat_comment(item)

    assert rendered.startswith("[12] ↳ reply in thread:")
    assert "parent: parent says" in rendered
    assert "· first reply" in rendered
    assert rendered.endswith("disagreed")


def test_render_user_message_includes_sources_and_comments():
    posts = [_post("https://a.com", content="post A body"), _post("https://b.com", content="post B body")]
    pool = Pool(
        items=[
            PoolItem(1, FlatComment("a1", 0, "alpha", [], 0)),
            PoolItem(2, FlatComment("b1", 0, "bravo", [], 1)),
        ],
        posts=posts,
    )

    msg = render_user_message(pool=pool, format_instruction="Format TITLE", hg_block=None)

    assert "POSTS (2 sources)" in msg
    assert "[Source 1 — FACEBOOK] https://a.com" in msg
    assert "post A body" in msg
    assert "[Source 2 — FACEBOOK] https://b.com" in msg
    assert "COMMENTS:" in msg
    assert "[1] alpha" in msg
    assert "[2] bravo" in msg
    assert "Format TITLE" in msg
    assert "After each bullet, append the citation markers" in msg


def test_render_user_message_with_hg_block():
    pool = Pool(items=[], posts=[_post("https://a.com")])

    msg = render_user_message(pool=pool, format_instruction="F", hg_block="BUCKET_LABELS_HERE")

    assert "BUCKET HOLY GRAIL REFERENCE:" in msg
    assert "BUCKET_LABELS_HERE" in msg
    assert msg.index("BUCKET HOLY GRAIL REFERENCE:") < msg.index("COMMENTS:")


def test_extract_citations_returns_records_for_cited_markers():
    pool = _pool_with_two_items()
    output = "- 50% discussed alpha [1]\n- 50% discussed bravo [2]"

    records = extract_citations_from_output(output, pool)

    assert len(records) == 2
    assert records[0] == CitationRecord(
        citation_number=1, text="alpha", comment_id="a1", position=0, source_index=0
    )
    assert records[1] == CitationRecord(
        citation_number=2, text="bravo", comment_id="b1", position=0, source_index=1
    )


def test_extract_citations_deduplicates_repeated_markers():
    pool = _pool_with_two_items()
    output = "- thing [1][2]\n- other thing [1]"

    records = extract_citations_from_output(output, pool)

    assert len(records) == 2
    assert sorted(r.citation_number for r in records) == [1, 2]


def test_extract_citations_ignores_unknown_markers():
    pool = _pool_with_two_items()
    output = "- alpha [1] and some [99] bogus"

    records = extract_citations_from_output(output, pool)

    assert [r.citation_number for r in records] == [1]


def test_extract_citations_empty_when_no_markers():
    pool = _pool_with_two_items()
    output = "no markers here"

    assert extract_citations_from_output(output, pool) == []


def test_run_prompt_analysis_returns_result():
    pool = _texture_pool()

    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="- 100% said alpha [1]")]

    with patch("autoso.pipeline.prompt_analysis.anthropic.Anthropic") as MockClient, patch(
        "autoso.pipeline.prompt_analysis.config"
    ) as MockConfig:
        MockConfig.ANTHROPIC_API_KEY = "sk-test"
        MockConfig.CLAUDE_MODEL = "claude-sonnet-4-6"
        MockConfig.USE_OLLAMA = False
        MockClient.return_value.messages.create.return_value = fake_response

        result = run_prompt_analysis(mode="texture", title="My Title", pool=pool, hg_block=None)

    assert isinstance(result, AnalysisResult)
    assert result.output_cited == "- 100% said alpha [1]"
    assert result.output_clean == "- 100% said alpha"
    assert [r.citation_number for r in result.citations] == [1]

    call_kwargs = MockClient.return_value.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-4-6"
    assert call_kwargs["system"].startswith("This GPT's role")
    assert call_kwargs["messages"][0]["role"] == "user"
    assert "My Title" in call_kwargs["messages"][0]["content"]
    assert "[1] alpha" in call_kwargs["messages"][0]["content"]


def test_run_prompt_analysis_bucket_mode_includes_hg_block():
    pool = _texture_pool()

    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="*Positive*\n1.  praised [1]")]

    with patch("autoso.pipeline.prompt_analysis.anthropic.Anthropic") as MockClient, patch(
        "autoso.pipeline.prompt_analysis.config"
    ) as MockConfig:
        MockConfig.ANTHROPIC_API_KEY = "sk-test"
        MockConfig.CLAUDE_MODEL = "claude-sonnet-4-6"
        MockConfig.USE_OLLAMA = False
        MockClient.return_value.messages.create.return_value = fake_response

        run_prompt_analysis(mode="bucket", title="T", pool=pool, hg_block="BUCKET_LABELS")

    call_kwargs = MockClient.return_value.messages.create.call_args.kwargs
    assert "BUCKET HOLY GRAIL REFERENCE:" in call_kwargs["messages"][0]["content"]
    assert "BUCKET_LABELS" in call_kwargs["messages"][0]["content"]


def test_run_prompt_analysis_raises_if_ollama_enabled():
    pool = _texture_pool()
    with patch("autoso.pipeline.prompt_analysis.config") as MockConfig:
        MockConfig.USE_OLLAMA = True
        try:
            run_prompt_analysis(mode="texture", title="T", pool=pool, hg_block=None)
        except RuntimeError as e:
            assert "prompt mode" in str(e).lower()
        else:
            raise AssertionError("expected RuntimeError")
