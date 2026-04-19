from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from autoso.scraping.models import Comment, Post
from autoso.storage.supabase import get_recent_scrape, store_result, store_scrape


def _sample_post() -> Post:
    dt = datetime(2026, 4, 18, 9, 0, tzinfo=timezone.utc)
    return Post(
        id="p1",
        platform="reddit",
        url="https://reddit.com/r/t/x",
        page_title="r/t",
        post_title="Title",
        date=dt,
        author="op",
        content="body",
        likes=5,
        comments=[
            Comment(
                id="c1",
                platform="reddit",
                author="a",
                date=dt,
                text="hi",
                likes=1,
                position=0,
            )
        ],
    )


@patch("autoso.storage.supabase._get_client")
def test_store_scrape_inserts_and_returns_id(mock_client):
    fake = MagicMock()
    mock_client.return_value = fake
    fake.table.return_value.insert.return_value.execute.return_value.data = [{"id": "uuid-1"}]

    post = _sample_post()
    scrape_id = store_scrape("https://reddit.com/r/t/x", post)

    assert isinstance(scrape_id, str)
    args = fake.table.return_value.insert.call_args.args[0]
    assert args["url"] == "https://reddit.com/r/t/x"
    assert args["result"]["id"] == "p1"
    assert args["result"]["comments"][0]["id"] == "c1"


@patch("autoso.storage.supabase._get_client")
def test_get_recent_scrape_returns_post_when_fresh(mock_client):
    fake = MagicMock()
    mock_client.return_value = fake
    post = _sample_post()
    recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    (
        fake.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value.data
    ) = [{"id": "uuid-1", "scraped_at": recent, "result": post.to_dict()}]

    result = get_recent_scrape("https://reddit.com/r/t/x")
    assert result is not None
    sid, p = result
    assert sid == "uuid-1"
    assert p.id == "p1"
    assert p.comments[0].id == "c1"


@patch("autoso.storage.supabase._get_client")
def test_get_recent_scrape_returns_none_when_no_rows(mock_client):
    fake = MagicMock()
    mock_client.return_value = fake
    (
        fake.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value.data
    ) = []

    assert get_recent_scrape("https://reddit.com/r/t/x") is None


@patch("autoso.storage.supabase._get_client")
def test_store_result_requires_scrape_id(mock_client):
    fake = MagicMock()
    mock_client.return_value = fake

    store_result(
        url="u",
        mode="texture",
        title="t",
        output="o",
        output_cited="oc",
        citation_index=[],
        scrape_id="uuid-1",
    )
    row = fake.table.return_value.insert.call_args_list[0].args[0]
    assert row["scrape_id"] == "uuid-1"
