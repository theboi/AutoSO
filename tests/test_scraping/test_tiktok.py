import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from autoso.scraping.models import Post
from autoso.scraping.tiktok import TikTokScraper, _extract_from_payload


def test_extract_from_payload_builds_nested_comments():
    payload = {
        "comments": [
            {
                "cid": "c1",
                "text": "First",
                "nickname": "user1",
                "create_time": 1713436800,
                "digg_count": 5,
                "reply_comment": [
                    {
                        "cid": "r1",
                        "text": "Reply",
                        "nickname": "user2",
                        "create_time": 1713436900,
                        "digg_count": 1,
                    }
                ],
            },
            {
                "cid": "c2",
                "text": "Second",
                "nickname": "user3",
                "create_time": 1713437000,
                "digg_count": 3,
                "reply_comment": [],
            },
        ]
    }
    comments = _extract_from_payload(payload, start_position=0)
    assert len(comments) == 2
    assert comments[0].id == "c1"
    assert comments[0].text == "First"
    assert comments[0].likes == 5
    assert len(comments[0].subcomments) == 1
    assert comments[0].subcomments[0].id == "r1"
    assert comments[1].subcomments == []


@pytest.mark.asyncio
@patch("autoso.scraping.tiktok.async_playwright")
@patch("autoso.scraping.tiktok.stealth_async", new_callable=AsyncMock)
async def test_scrape_empty_when_no_xhr_intercepted(mock_stealth, mock_pw):
    scraper = TikTokScraper()
    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = MagicMock()
    mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_pw.return_value)
    mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_pw.return_value.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.storage_state = AsyncMock(return_value={})

    mock_page.goto = AsyncMock()
    mock_page.url = "https://www.tiktok.com/@mindef/video/123"
    mock_page.content = AsyncMock(return_value="<html></html>")
    mock_page.on = MagicMock()
    mock_page.evaluate = AsyncMock(return_value=None)

    empty = MagicMock()
    empty.is_visible = AsyncMock(return_value=False)
    empty.get_attribute = AsyncMock(return_value=None)
    empty.inner_text = AsyncMock(return_value="")
    empty.first = empty
    empty.nth = MagicMock(return_value=empty)
    empty.count = AsyncMock(return_value=0)

    mock_page.locator = MagicMock(return_value=empty)

    post = await scraper._scrape_async("https://www.tiktok.com/@mindef/video/123")
    assert isinstance(post, Post)
    assert post.platform == "tiktok"
    assert post.comments == []
