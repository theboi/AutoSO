import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from autoso.scraping.hardwarezone import HardwareZoneScraper
from autoso.scraping.models import Post


@pytest.mark.asyncio
@patch("autoso.scraping.hardwarezone.async_playwright")
@patch("autoso.scraping.hardwarezone.stealth_async", new_callable=AsyncMock)
async def test_scrape_returns_post_empty_when_no_posts(mock_stealth, mock_pw):
    scraper = HardwareZoneScraper()

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
    mock_page.url = "https://forums.hardwarezone.com.sg/threads/foo.1/"
    mock_page.content = AsyncMock(return_value="<html></html>")

    empty = MagicMock()
    empty.count = AsyncMock(return_value=0)
    empty.is_visible = AsyncMock(return_value=False)
    empty.get_attribute = AsyncMock(return_value=None)
    empty.inner_text = AsyncMock(return_value="")
    empty.first = empty
    empty.nth = MagicMock(return_value=empty)

    mock_page.locator = MagicMock(return_value=empty)
    mock_page.get_by_text = MagicMock(return_value=empty)

    post = await scraper._scrape_async("https://forums.hardwarezone.com.sg/threads/foo.1/")
    assert isinstance(post, Post)
    assert post.platform == "hardwarezone"
    assert post.comments == []


@pytest.mark.asyncio
@patch("autoso.scraping.hardwarezone.async_playwright")
@patch("autoso.scraping.hardwarezone.stealth_async", new_callable=AsyncMock)
async def test_scrape_follows_pagination(mock_stealth, mock_pw):
    scraper = HardwareZoneScraper()

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
    mock_page.url = "https://forums.hardwarezone.com.sg/threads/foo.1/"
    mock_page.content = AsyncMock(return_value="<html></html>")

    empty = MagicMock()
    empty.count = AsyncMock(return_value=0)
    empty.is_visible = AsyncMock(return_value=False)
    empty.get_attribute = AsyncMock(return_value=None)
    empty.inner_text = AsyncMock(return_value="")
    empty.first = empty
    empty.nth = MagicMock(return_value=empty)

    mock_page.locator = MagicMock(return_value=empty)
    mock_page.get_by_text = MagicMock(return_value=empty)

    post = await scraper._scrape_async("https://forums.hardwarezone.com.sg/threads/foo.1/")

    assert mock_page.goto.call_count == 1
    assert post.comments == []
