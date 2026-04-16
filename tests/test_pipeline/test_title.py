# tests/test_pipeline/test_title.py
from unittest.mock import MagicMock, patch
from autoso.scraping.models import Comment, Post
from autoso.pipeline.title import infer_title


def _make_post(content: str, comments: list[str]) -> Post:
    return Post(
        title="",
        content=content,
        url="https://reddit.com/r/test/comments/abc",
        platform="reddit",
        comments=[
            Comment(platform="reddit", text=t, comment_id=f"c{i}", position=i)
            for i, t in enumerate(comments)
        ],
    )


def test_infer_title_returns_string():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = MagicMock(text="NS Training Exercise")

    with patch("autoso.pipeline.title.Settings") as mock_settings:
        mock_settings.llm = mock_llm
        post = _make_post("XLS25 exercise underway", ["Great exercise", "SAF looks strong"])
        result = infer_title(post)

    assert isinstance(result, str)
    assert len(result) > 0


def test_infer_title_strips_quotes():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = MagicMock(text='"NS Training Debate"')

    with patch("autoso.pipeline.title.Settings") as mock_settings:
        mock_settings.llm = mock_llm
        post = _make_post("Post content", ["Comment 1"])
        result = infer_title(post)

    assert not result.startswith('"')
    assert not result.endswith('"')


def test_infer_title_includes_platform_in_prompt():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = MagicMock(text="Test Title")
    captured_prompts = []

    def capture(prompt):
        captured_prompts.append(prompt)
        return MagicMock(text="Test Title")

    mock_llm.complete.side_effect = capture

    with patch("autoso.pipeline.title.Settings") as mock_settings:
        mock_settings.llm = mock_llm
        post = _make_post("content", ["comment"])
        post.platform = "instagram"
        infer_title(post)

    assert "instagram" in captured_prompts[0].lower()
