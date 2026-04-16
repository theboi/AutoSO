from unittest.mock import patch, MagicMock
from autoso.scraping.base import get_scraper
from autoso.scraping.reddit import RedditScraper
from autoso.scraping.instagram import InstagramScraper
from autoso.scraping.facebook import FacebookScraper
import pytest


@patch("autoso.scraping.reddit.praw.Reddit")
def test_factory_returns_reddit_scraper(mock_reddit):
    s = get_scraper("https://www.reddit.com/r/singapore/comments/abc")
    assert isinstance(s, RedditScraper)


def test_factory_returns_instagram_scraper():
    s = get_scraper("https://www.instagram.com/p/ABC123/")
    assert isinstance(s, InstagramScraper)


def test_factory_returns_facebook_scraper():
    s = get_scraper("https://www.facebook.com/mindef/posts/123")
    assert isinstance(s, FacebookScraper)


def test_factory_raises_for_unsupported_url():
    with pytest.raises(ValueError, match="Unsupported platform"):
        get_scraper("https://twitter.com/mindef/status/1")
