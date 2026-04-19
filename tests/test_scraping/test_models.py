from datetime import datetime, timezone

from autoso.scraping.models import Comment, Post, ScrapeError


def test_comment_construction_with_all_fields():
    dt = datetime(2026, 4, 18, 10, 30, tzinfo=timezone.utc)
    c = Comment(
        id="fb_0",
        platform="facebook",
        author="Alice",
        date=dt,
        text="Hello",
        likes=5,
        position=0,
    )
    assert c.id == "fb_0"
    assert c.author == "Alice"
    assert c.date == dt
    assert c.likes == 5
    assert c.subcomments == []


def test_comment_optional_fields_default_to_none():
    c = Comment(
        id="x",
        platform="reddit",
        author=None,
        date=None,
        text="hi",
        likes=None,
        position=0,
    )
    assert c.author is None
    assert c.date is None
    assert c.likes is None


def test_comment_with_subcomments():
    reply = Comment(
        id="r1", platform="reddit", author="Bob", date=None, text="reply", likes=1, position=0
    )
    parent = Comment(
        id="p1",
        platform="reddit",
        author="Alice",
        date=None,
        text="parent",
        likes=2,
        position=0,
        subcomments=[reply],
    )
    assert len(parent.subcomments) == 1
    assert parent.subcomments[0].text == "reply"


def test_post_construction_with_all_fields():
    dt = datetime(2026, 4, 18, 9, 0, tzinfo=timezone.utc)
    post = Post(
        id="fb_123",
        platform="facebook",
        url="https://facebook.com/mindef/posts/123",
        page_title="MINDEF Singapore | Facebook",
        post_title="NS Announcement",
        date=dt,
        author="MINDEF",
        content="Post body",
        likes=42,
        comments=[],
    )
    assert post.id == "fb_123"
    assert post.page_title == "MINDEF Singapore | Facebook"
    assert post.likes == 42
    assert post.comments == []


def test_comment_to_dict_round_trip():
    dt = datetime(2026, 4, 18, 10, 30, tzinfo=timezone.utc)
    reply = Comment(
        id="r1", platform="reddit", author="Bob", date=dt, text="reply", likes=1, position=0
    )
    c = Comment(
        id="c1",
        platform="reddit",
        author="Alice",
        date=dt,
        text="parent",
        likes=5,
        position=0,
        subcomments=[reply],
    )
    d = c.to_dict()
    assert d["id"] == "c1"
    assert d["date"] == "2026-04-18T10:30:00+00:00"
    assert d["subcomments"][0]["id"] == "r1"

    restored = Comment.from_dict(d)
    assert restored == c


def test_comment_from_dict_handles_null_date():
    d = {
        "id": "c1",
        "platform": "reddit",
        "author": None,
        "date": None,
        "text": "hi",
        "likes": None,
        "position": 0,
        "subcomments": [],
    }
    c = Comment.from_dict(d)
    assert c.date is None
    assert c.likes is None


def test_post_to_dict_round_trip():
    dt = datetime(2026, 4, 18, 9, 0, tzinfo=timezone.utc)
    c = Comment(id="c1", platform="reddit", author="Alice", date=dt, text="hi", likes=1, position=0)
    post = Post(
        id="p1",
        platform="reddit",
        url="https://reddit.com/r/test/x",
        page_title="r/test",
        post_title="Test",
        date=dt,
        author="op",
        content="body",
        likes=10,
        comments=[c],
    )
    d = post.to_dict()
    assert d["id"] == "p1"
    assert d["comments"][0]["id"] == "c1"

    restored = Post.from_dict(d)
    assert restored == post


def test_scrape_error_still_works():
    err = ScrapeError("boom", cause="timeout")
    assert err.cause == "timeout"
