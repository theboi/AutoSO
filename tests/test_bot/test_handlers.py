# tests/test_bot/test_handlers.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from autoso.bot.handlers import (
    ArgParseError,
    _parse_analysis_args,
    bucket_handler,
    start_handler,
    texture_handler,
)
from autoso.pipeline.pipeline import PipelineResult


def _make_update(user_id: int, args: list[str]):
    update = MagicMock()
    update.effective_user.id = user_id
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = args
    return update, context


@pytest.fixture(autouse=True)
def whitelist_user():
    with patch("autoso.config.WHITELISTED_USER_IDS", {99}):
        yield


async def test_start_handler_replies():
    update, context = _make_update(99, [])
    await start_handler(update, context)
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args.args[0]
    assert "/texture" in text
    assert "/bucket" in text
    assert "-m prompt|rag" in text


async def test_texture_handler_no_args_sends_usage():
    update, context = _make_update(99, [])
    await texture_handler(update, context)
    text = update.message.reply_text.call_args.args[0]
    assert "Usage" in text


async def test_texture_handler_calls_pipeline_and_replies():
    update, context = _make_update(99, ["https://reddit.com/r/sg/comments/abc"])
    mock_result = PipelineResult(
        title="Test",
        output="- 50% praised SAF",
        output_cited="- 50% praised SAF [1]",
        run_id="run-abc",
    )
    with patch("autoso.bot.handlers.run_pipeline", return_value=mock_result) as mock_pipeline:
        await texture_handler(update, context)

    mock_pipeline.assert_called_once_with(
        urls=["https://reddit.com/r/sg/comments/abc"],
        mode="texture",
        analysis_mode="prompt",
        provided_title=None,
    )
    calls = [str(c) for c in update.message.reply_text.call_args_list]
    assert any("Processing 1 link(s) with prompt mode" in c for c in calls)
    assert any("praised SAF" in c for c in calls)


async def test_handler_notifies_user_when_output_too_long():
    update, context = _make_update(99, ["https://reddit.com/r/sg/comments/abc"])
    long_output = "x" * 5000
    mock_result = PipelineResult(
        title="Test",
        output=long_output,
        output_cited=long_output,
        run_id="run-abc",
    )
    with patch("autoso.bot.handlers.run_pipeline", return_value=mock_result) as mock_pipeline:
        await texture_handler(update, context)

    mock_pipeline.assert_called_once_with(
        urls=["https://reddit.com/r/sg/comments/abc"],
        mode="texture",
        analysis_mode="prompt",
        provided_title=None,
    )
    calls = [str(c) for c in update.message.reply_text.call_args_list]
    assert any("too long" in c for c in calls) or any("5000" in c for c in calls)
    assert any("run-abc" in c for c in calls)


async def test_handler_replies_on_pipeline_exception():
    update, context = _make_update(99, ["https://reddit.com/r/sg/comments/abc"])
    with patch("autoso.bot.handlers.run_pipeline", side_effect=RuntimeError("scrape failed")):
        await texture_handler(update, context)

    calls = [str(c) for c in update.message.reply_text.call_args_list]
    assert any("error" in c.lower() for c in calls)


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (
            ["https://a.com"],
            (["https://a.com"], "prompt", None),
        ),
        (
            ["https://a.com", "https://b.com", "-m", "rag"],
            (["https://a.com", "https://b.com"], "rag", None),
        ),
        (
            ["https://a.com", '"My', "Quoted", 'Title"'],
            (["https://a.com"], "prompt", "My Quoted Title"),
        ),
        (
            ["https://a.com", "-m", "prompt", "'Single token title'"],
            (["https://a.com"], "prompt", "Single token title"),
        ),
    ],
)
def test_parse_analysis_args_valid(args, expected):
    assert _parse_analysis_args(args) == expected


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["-m"],
        ["-m", "bad"],
        ["title-only"],
        ["https://a.com", "--unknown"],
        ["https://a.com", '"unterminated', "title"],
        ["https://a.com", "stray"],
        ["https://a.com", '"one"', '"two"'],
        [f"https://{i}.example.com" for i in range(51)],
    ],
)
def test_parse_analysis_args_invalid(args):
    with pytest.raises(ArgParseError):
        _parse_analysis_args(args)


async def test_bucket_handler_multi_url_rag_and_quoted_title():
    update, context = _make_update(
        99,
        [
            "https://a.com/post",
            "https://b.com/post",
            "-m",
            "rag",
            '"My',
            "Custom",
            'Title"',
        ],
    )
    mock_result = PipelineResult(
        title="My Custom Title",
        output="Result body",
        output_cited="Result body [1]",
        run_id="run-rag",
    )
    with patch("autoso.bot.handlers.run_pipeline", return_value=mock_result) as mock_pipeline:
        await bucket_handler(update, context)

    mock_pipeline.assert_called_once_with(
        urls=["https://a.com/post", "https://b.com/post"],
        mode="bucket",
        analysis_mode="rag",
        provided_title="My Custom Title",
    )
    calls = [str(c) for c in update.message.reply_text.call_args_list]
    assert any("Processing 2 link(s) with rag mode" in c for c in calls)
    assert any("Result body" in c for c in calls)
