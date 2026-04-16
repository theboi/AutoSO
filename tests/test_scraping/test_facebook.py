import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from autoso.scraping.facebook import FacebookScraper
from autoso.scraping.models import Post


@pytest.mark.asyncio
@patch("autoso.scraping.facebook.async_playwright")
@patch("autoso.scraping.facebook.stealth_async", new_callable=AsyncMock)
async def test_scrape_returns_post(mock_stealth, mock_pw):
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

    post_el = AsyncMock()
    post_el.inner_text = AsyncMock(return_value="FB post body")
    post_loc = MagicMock()
    post_loc.first = post_el

    title_el = AsyncMock()
    title_el.get_attribute = AsyncMock(return_value="FB Post")
    title_loc = MagicMock()
    title_loc.get_attribute = AsyncMock(return_value="FB Post")

    load_more = AsyncMock()
    load_more.is_visible = AsyncMock(return_value=False)
    mock_page.get_by_text.return_value.first = load_more

    comment_texts = ["SAF exercise was great", "Good bilateral relations"]

    def make_text_el(text):
        el = MagicMock()
        el.inner_text = AsyncMock(return_value=text)
        return el

    async def async_count():
        return len(comment_texts)

    comment_loc = MagicMock()
    comment_loc.count = AsyncMock(side_effect=async_count)
    comment_loc.nth = MagicMock(side_effect=lambda i: make_text_el(comment_texts[i]))

    selector_map = {
        "[data-ad-comet-preview='message'], [data-testid='post_message']": post_loc,
        "meta[property='og:title']": title_loc,
        "[aria-label='Comment'] span[dir='auto']": comment_loc,
    }

    def locator_side_effect(selector):
        return selector_map.get(selector, MagicMock())

    mock_page.locator.side_effect = locator_side_effect
    mock_page.goto = AsyncMock(return_value=None)
    mock_page.url = "https://www.facebook.com/mindef/posts/123"
    mock_page.content = AsyncMock(return_value="<html></html>")

    post = await scraper._scrape_async("https://www.facebook.com/mindef/posts/123")

    assert isinstance(post, Post)
    assert post.platform == "facebook"
    assert post.url == "https://www.facebook.com/mindef/posts/123"
