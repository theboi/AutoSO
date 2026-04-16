import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from autoso.scraping.instagram import InstagramScraper
from autoso.scraping.models import Post, Comment


def _make_text_el(text: str) -> MagicMock:
    el = MagicMock()
    el.inner_text = AsyncMock(return_value=text)
    return el


def _make_locator_for(texts: list[str]) -> MagicMock:
    """Return a mock locator whose .nth(i).inner_text() yields texts[i]."""
    async def async_count():
        return len(texts)

    loc = AsyncMock()
    loc.count = AsyncMock(side_effect=async_count)
    loc.nth = MagicMock(side_effect=lambda i: _make_text_el(texts[i]))
    return loc


def _build_page_mock(
    post_content: str,
    og_title: str,
    comment_texts: list[str],
    load_more_visible: bool = False,
) -> MagicMock:
    page = MagicMock()

    # post content: article ... span selector → .first.inner_text()
    post_el = AsyncMock()
    post_el.inner_text = AsyncMock(return_value=post_content)
    post_loc = MagicMock()
    post_loc.first = post_el

    # og:title: meta[property='og:title'] → .get_attribute("content")
    title_el = AsyncMock()
    title_el.get_attribute = AsyncMock(return_value=og_title)
    title_loc = MagicMock()
    title_loc.__aiter__ = MagicMock(return_value=iter([title_el]))
    title_loc.get_attribute = AsyncMock(return_value=og_title)

    # comments: article ul li span[dir='auto'] → .count() / .nth(i)
    comment_loc = _make_locator_for(comment_texts)

    selector_map = {
        "article h1, article div[data-testid='post-content'], article span": post_loc,
        "meta[property='og:title']": title_loc,
        "article ul li span[dir='auto']": comment_loc,
    }

    def locator_side_effect(selector):
        return selector_map.get(selector, MagicMock())

    page.locator.side_effect = locator_side_effect
    page.goto = AsyncMock(return_value=None)
    page.url = "https://www.instagram.com/p/ABC123/"

    # _expand_comments: get_by_text("Load more comments").first.is_visible()
    load_more = AsyncMock()
    load_more.is_visible = AsyncMock(return_value=load_more_visible)
    page.get_by_text.return_value.first = load_more

    return page


@pytest.mark.asyncio
@patch("autoso.scraping.instagram.async_playwright")
@patch("autoso.scraping.instagram.stealth_async", new_callable=AsyncMock)
async def test_scrape_returns_post_with_correct_platform(mock_stealth, mock_pw):
    """_scrape_async returns a Post with platform='instagram' and correct URL."""
    scraper = InstagramScraper()
    comment_texts = [
        "Great photo from the SAF exercise!",
        "Really proud of our NSmen",
        "Amazing bilateral relations event",
    ]
    mock_page = _build_page_mock(
        post_content="SAF event post body",
        og_title="SAF Event",
        comment_texts=comment_texts,
    )

    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_context.storage_state = AsyncMock(return_value={})
    mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_pw.return_value)
    mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_pw.return_value.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.new_page = AsyncMock(return_value=mock_page)

    url = "https://www.instagram.com/p/ABC123/"
    post = await scraper._scrape_async(url)

    assert isinstance(post, Post)
    assert post.platform == "instagram"
    assert post.url == url


@pytest.mark.asyncio
@patch("autoso.scraping.instagram.async_playwright")
@patch("autoso.scraping.instagram.stealth_async", new_callable=AsyncMock)
async def test_scrape_extracts_comments(mock_stealth, mock_pw):
    """Comments longer than 10 chars are extracted into the Post."""
    scraper = InstagramScraper()
    comment_texts = [
        "NS training builds character and discipline",
        "SAF personnel were very professional",
        "ok",  # too short, must be filtered out
    ]
    mock_page = _build_page_mock(
        post_content="Post body",
        og_title="Title",
        comment_texts=comment_texts,
    )

    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_context.storage_state = AsyncMock(return_value={})
    mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_pw.return_value)
    mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_pw.return_value.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.new_page = AsyncMock(return_value=mock_page)

    post = await scraper._scrape_async("https://www.instagram.com/p/XYZ/")

    extracted_texts = [c.text for c in post.comments]
    assert "NS training builds character and discipline" in extracted_texts
    assert "SAF personnel were very professional" in extracted_texts
    assert "ok" not in extracted_texts
    assert len(post.comments) == 2
