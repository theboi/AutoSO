from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from autoso.scraping import flatten_comments, scrape
from autoso.scraping.models import Comment, Post


def _sample_post() -> Post:
    dt = datetime(2026, 4, 18, 9, 0, tzinfo=timezone.utc)
    reply = Comment(
        id="r1",
        platform="reddit",
        author="b",
        date=dt,
        text="reply",
        likes=1,
        position=0,
    )
    parent = Comment(
        id="c1",
        platform="reddit",
        author="a",
        date=dt,
        text="parent",
        likes=2,
        position=0,
        subcomments=[reply],
    )
    top = Comment(
        id="c2",
        platform="reddit",
        author="c",
        date=dt,
        text="top2",
        likes=3,
        position=1,
    )
    return Post(
        id="p1",
        platform="reddit",
        url="https://reddit.com/r/t/x",
        page_title="r/t",
        post_title="T",
        date=dt,
        author="op",
        content="body",
        likes=5,
        comments=[parent, top],
    )


@patch("autoso.scraping.get_recent_scrape")
@patch("autoso.scraping.get_scraper")
@patch("autoso.scraping.store_scrape")
def test_scrape_returns_cached_post_on_hit(mock_store, mock_factory, mock_get_recent):
    post = _sample_post()
    mock_get_recent.return_value = ("cached-sid", post)

    scrape_id, result = scrape("https://reddit.com/r/t/x")

    assert scrape_id == "cached-sid"
    assert result is post
    mock_factory.assert_not_called()
    mock_store.assert_not_called()


@patch("autoso.scraping.get_recent_scrape")
@patch("autoso.scraping.get_scraper")
@patch("autoso.scraping.store_scrape")
def test_scrape_invokes_scraper_and_stores_on_miss(mock_store, mock_factory, mock_get_recent):
    post = _sample_post()
    mock_get_recent.return_value = None
    mock_scraper = MagicMock()
    mock_scraper.scrape.return_value = post
    mock_factory.return_value = mock_scraper
    mock_store.return_value = "new-sid"

    scrape_id, result = scrape("https://reddit.com/r/t/x")

    assert scrape_id == "new-sid"
    assert result is post
    mock_scraper.scrape.assert_called_once_with("https://reddit.com/r/t/x")
    mock_store.assert_called_once_with("https://reddit.com/r/t/x", post)


def test_flatten_comments_returns_all_comments_depth_first():
    post = _sample_post()
    flat = flatten_comments(post)
    assert len(flat) == 3
    assert flat[0].id == "c1"
    assert flat[1].id == "r1"
    assert flat[2].id == "c2"


def test_flatten_comments_empty_when_no_comments():
    dt = datetime(2026, 4, 18, tzinfo=timezone.utc)
    post = Post(
        id="p",
        platform="reddit",
        url="u",
        page_title="",
        post_title="",
        date=dt,
        author=None,
        content=None,
        likes=None,
        comments=[],
    )
    assert flatten_comments(post) == []
