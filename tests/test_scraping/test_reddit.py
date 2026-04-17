import pytest
from unittest.mock import MagicMock, patch
from autoso.scraping.reddit import RedditScraper
from autoso.scraping.models import Post, Comment


def _make_mock_comment(body: str, id: str, pos: int) -> MagicMock:
    c = MagicMock()
    c.body = body
    c.id = id
    return c


def _make_mock_submission(title: str, selftext: str, comments: list) -> MagicMock:
    sub = MagicMock()
    sub.title = title
    sub.selftext = selftext
    sub.comments.list.return_value = comments
    sub.comments.replace_more = MagicMock()
    return sub


@patch("autoso.scraping.reddit.praw.Reddit")
def test_scrape_returns_post(mock_reddit_cls):
    raw_comments = [
        _make_mock_comment("NS is important for defence", "c1", 0),
        _make_mock_comment("I support MINDEF policies", "c2", 1),
    ]
    sub = _make_mock_submission("Test Post", "Post body here", raw_comments)
    mock_reddit_cls.return_value.submission.return_value = sub

    scraper = RedditScraper()
    post = scraper.scrape("https://www.reddit.com/r/singapore/comments/abc")

    assert isinstance(post, Post)
    assert post.platform == "reddit"
    assert post.title == "Test Post"
    assert post.content == "Post body here"
    assert len(post.comments) == 2
    assert post.comments[0].text == "NS is important for defence"
    assert post.comments[0].comment_id == "c1"
    assert post.comments[0].position == 0
    assert post.comments[1].position == 1


@patch("autoso.scraping.reddit.praw.Reddit")
def test_scrape_filters_deleted_comments(mock_reddit_cls):
    raw_comments = [
        _make_mock_comment("[deleted]", "d1", 0),
        _make_mock_comment("[removed]", "d2", 1),
        _make_mock_comment("Normal comment", "c1", 2),
    ]
    sub = _make_mock_submission("Post", "", raw_comments)
    mock_reddit_cls.return_value.submission.return_value = sub

    scraper = RedditScraper()
    post = scraper.scrape("https://www.reddit.com/r/test/comments/xyz")

    assert len(post.comments) == 1
    assert post.comments[0].text == "Normal comment"


@patch("autoso.scraping.reddit.praw.Reddit")
def test_scrape_uses_title_as_content_when_no_selftext(mock_reddit_cls):
    raw_comments = [_make_mock_comment("Good point", "c1", 0)]
    sub = _make_mock_submission("Link Post Title", "", raw_comments)
    mock_reddit_cls.return_value.submission.return_value = sub

    scraper = RedditScraper()
    post = scraper.scrape("https://www.reddit.com/r/test/comments/xyz")

    assert post.content == "Link Post Title"


@patch("autoso.scraping.reddit.praw.Reddit")
def test_scrape_keeps_comment_starting_with_deleted_word_in_context(mock_reddit_cls):
    """A real comment that starts with the word 'deleted' in context must NOT be filtered."""
    raw_comments = [
        _make_mock_comment("[deleted] is a common meme response", "c1", 0),  # should be filtered
        _make_mock_comment("The deleted scene was actually good", "c2", 1),  # must be kept
    ]
    sub = _make_mock_submission("Post", "body", raw_comments)
    mock_reddit_cls.return_value.submission.return_value = sub

    scraper = RedditScraper()
    post = scraper.scrape("https://www.reddit.com/r/test/comments/xyz")

    texts = [c.text for c in post.comments]
    assert "[deleted] is a common meme response" not in texts  # exact match filtered
    assert "The deleted scene was actually good" in texts       # partial match kept


@patch("autoso.scraping.reddit.praw.Reddit")
def test_scrape_positions_are_sequential_after_filtering(mock_reddit_cls):
    """Positions must be 0-indexed and contiguous after deleted comments are dropped."""
    raw_comments = [
        _make_mock_comment("[deleted]", "d1", 0),
        _make_mock_comment("First real comment", "c1", 1),
        _make_mock_comment("Second real comment", "c2", 2),
    ]
    sub = _make_mock_submission("Post", "body", raw_comments)
    mock_reddit_cls.return_value.submission.return_value = sub

    scraper = RedditScraper()
    post = scraper.scrape("https://www.reddit.com/r/test/comments/xyz")

    assert len(post.comments) == 2
    assert post.comments[0].position == 1  # position reflects original list index
    assert post.comments[1].position == 2
