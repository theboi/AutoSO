from unittest.mock import MagicMock, patch

from autoso.scraping.models import Post
from autoso.scraping.reddit import RedditScraper


def _reddit_json(post_data: dict, comments: list[dict]) -> list:
    post_listing = {"data": {"children": [{"kind": "t3", "data": post_data}]}}
    comment_listing = {
        "data": {"children": [{"kind": "t1", "data": c} for c in comments]}
    }
    return [post_listing, comment_listing]


def _mock_response(json_payload):
    resp = MagicMock()
    resp.json.return_value = json_payload
    resp.raise_for_status = MagicMock()
    return resp


@patch("autoso.scraping.reddit.httpx.get")
def test_scrape_builds_post_from_json(mock_get):
    post_data = {
        "id": "abc123",
        "title": "Test Post",
        "selftext": "Post body",
        "author": "op_user",
        "score": 42,
        "created_utc": 1713436800,
        "subreddit_name_prefixed": "r/singapore",
    }
    comments = [
        {
            "id": "c1",
            "body": "First comment",
            "author": "user1",
            "score": 5,
            "created_utc": 1713436900,
            "replies": "",
        },
        {
            "id": "c2",
            "body": "Second comment",
            "author": "user2",
            "score": 3,
            "created_utc": 1713437000,
            "replies": {
                "data": {
                    "children": [
                        {
                            "kind": "t1",
                            "data": {
                                "id": "r1",
                                "body": "Reply",
                                "author": "user3",
                                "score": 1,
                                "created_utc": 1713437050,
                                "replies": "",
                            },
                        }
                    ]
                }
            },
        },
    ]
    mock_get.return_value = _mock_response(_reddit_json(post_data, comments))

    scraper = RedditScraper()
    post = scraper.scrape("https://www.reddit.com/r/singapore/comments/abc123/test/")

    assert isinstance(post, Post)
    assert post.platform == "reddit"
    assert post.id == "abc123"
    assert post.post_title == "Test Post"
    assert post.content == "Post body"
    assert post.author == "op_user"
    assert post.likes == 42
    assert post.page_title == "r/singapore"
    assert post.date is not None
    assert len(post.comments) == 2
    assert post.comments[0].id == "c1"
    assert post.comments[0].author == "user1"
    assert post.comments[0].text == "First comment"
    assert post.comments[0].likes == 5
    assert post.comments[0].position == 0
    assert post.comments[0].subcomments == []
    assert len(post.comments[1].subcomments) == 1
    assert post.comments[1].subcomments[0].id == "r1"
    assert post.comments[1].subcomments[0].text == "Reply"


@patch("autoso.scraping.reddit.httpx.get")
def test_scrape_filters_deleted_and_removed(mock_get):
    comments = [
        {
            "id": "d1",
            "body": "[deleted]",
            "author": "[deleted]",
            "score": 0,
            "created_utc": 1713436900,
            "replies": "",
        },
        {
            "id": "d2",
            "body": "[removed]",
            "author": "mod",
            "score": 0,
            "created_utc": 1713437000,
            "replies": "",
        },
        {
            "id": "c1",
            "body": "Normal",
            "author": "u",
            "score": 1,
            "created_utc": 1713437100,
            "replies": "",
        },
    ]
    post_data = {
        "id": "x",
        "title": "T",
        "selftext": "",
        "author": "op",
        "score": 1,
        "created_utc": 1,
        "subreddit_name_prefixed": "r/t",
    }
    mock_get.return_value = _mock_response(_reddit_json(post_data, comments))

    scraper = RedditScraper()
    post = scraper.scrape("https://www.reddit.com/r/t/comments/x/y/")

    assert len(post.comments) == 1
    assert post.comments[0].text == "Normal"


@patch("autoso.scraping.reddit.httpx.get")
def test_scrape_skips_more_kind_nodes(mock_get):
    post_data = {
        "id": "x",
        "title": "T",
        "selftext": "",
        "author": "op",
        "score": 1,
        "created_utc": 1,
        "subreddit_name_prefixed": "r/t",
    }
    payload = [
        {"data": {"children": [{"kind": "t3", "data": post_data}]}},
        {
            "data": {
                "children": [
                    {
                        "kind": "t1",
                        "data": {
                            "id": "c1",
                            "body": "hi",
                            "author": "u",
                            "score": 1,
                            "created_utc": 2,
                            "replies": "",
                        },
                    },
                    {"kind": "more", "data": {"count": 100}},
                ]
            }
        },
    ]
    mock_get.return_value = _mock_response(payload)

    scraper = RedditScraper()
    post = scraper.scrape("https://www.reddit.com/r/t/comments/x/y/")

    assert len(post.comments) == 1


@patch("autoso.scraping.reddit.httpx.get")
def test_scrape_appends_json_suffix(mock_get):
    post_data = {
        "id": "x",
        "title": "T",
        "selftext": "",
        "author": "op",
        "score": 1,
        "created_utc": 1,
        "subreddit_name_prefixed": "r/t",
    }
    mock_get.return_value = _mock_response(_reddit_json(post_data, []))

    scraper = RedditScraper()
    scraper.scrape("https://www.reddit.com/r/t/comments/x/y/")

    called_url = mock_get.call_args.args[0]
    assert called_url.endswith(".json")
