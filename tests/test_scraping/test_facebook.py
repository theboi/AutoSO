import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from autoso.scraping.facebook import FacebookScraper
from autoso.scraping.models import Post


def _empty_locator() -> AsyncMock:
    loc = AsyncMock()
    loc.count = AsyncMock(return_value=0)
    loc.inner_text = AsyncMock(return_value="")
    loc.get_attribute = AsyncMock(return_value=None)
    loc.is_visible = AsyncMock(return_value=False)
    loc.bounding_box = AsyncMock(return_value=None)
    loc.evaluate = AsyncMock(return_value=False)
    loc.first = loc
    loc.last = loc
    loc.nth = MagicMock(return_value=loc)
    return loc


@pytest.mark.asyncio
@patch("autoso.scraping.facebook.async_playwright")
@patch("autoso.scraping.facebook.stealth_async", new_callable=AsyncMock)
async def test_scrape_returns_post_with_new_fields(mock_stealth, mock_pw):
    scraper = FacebookScraper()

    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = MagicMock()
    mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_pw.return_value)
    mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_pw.return_value.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.storage_state = AsyncMock(return_value={})

    mock_page.goto = AsyncMock(return_value=None)
    mock_page.url = "https://www.facebook.com/mindef/posts/123"
    mock_page.content = AsyncMock(return_value="<html></html>")
    mock_page.evaluate = AsyncMock(return_value=None)
    mock_page.mouse.move = AsyncMock()
    mock_page.mouse.wheel = AsyncMock()

    empty = _empty_locator()
    mock_page.locator = MagicMock(return_value=empty)
    mock_page.get_by_text = MagicMock(return_value=empty)

    post = await scraper._scrape_async("https://www.facebook.com/mindef/posts/123")

    assert isinstance(post, Post)
    assert post.platform == "facebook"
    assert post.url == "https://www.facebook.com/mindef/posts/123"
    assert post.id.startswith("fb_")
    assert post.page_title is not None
    assert post.post_title is not None
    assert post.likes is None or isinstance(post.likes, int)
    assert post.comments == []
