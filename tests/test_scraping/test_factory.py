import pytest

from autoso.scraping.base import detect_platform, get_scraper


def test_detect_platform_reddit():
    assert detect_platform("https://www.reddit.com/r/singapore/comments/abc") == "reddit"


def test_detect_platform_instagram():
    assert detect_platform("https://www.instagram.com/p/ABC123/") == "instagram"


def test_detect_platform_facebook():
    assert detect_platform("https://www.facebook.com/mindef/posts/123") == "facebook"


def test_detect_platform_hardwarezone():
    assert (
        detect_platform("https://forums.hardwarezone.com.sg/threads/foo.1234/")
        == "hardwarezone"
    )


def test_detect_platform_youtube_long():
    assert detect_platform("https://www.youtube.com/watch?v=abc") == "youtube"


def test_detect_platform_youtube_short():
    assert detect_platform("https://youtu.be/abc") == "youtube"


def test_detect_platform_tiktok():
    assert detect_platform("https://www.tiktok.com/@user/video/123") == "tiktok"


def test_detect_platform_unsupported_raises():
    with pytest.raises(ValueError, match="Unsupported platform"):
        detect_platform("https://twitter.com/x/status/1")


def test_get_scraper_returns_correct_type():
    from autoso.scraping.facebook import FacebookScraper
    from autoso.scraping.hardwarezone import HardwareZoneScraper
    from autoso.scraping.instagram import InstagramScraper
    from autoso.scraping.reddit import RedditScraper
    from autoso.scraping.tiktok import TikTokScraper
    from autoso.scraping.youtube import YouTubeScraper

    assert isinstance(get_scraper("https://reddit.com/r/x/comments/y"), RedditScraper)
    assert isinstance(get_scraper("https://instagram.com/p/ABC/"), InstagramScraper)
    assert isinstance(get_scraper("https://facebook.com/m/posts/1"), FacebookScraper)
    assert isinstance(
        get_scraper("https://forums.hardwarezone.com.sg/threads/a.1/"),
        HardwareZoneScraper,
    )
    assert isinstance(get_scraper("https://youtube.com/watch?v=a"), YouTubeScraper)
    assert isinstance(get_scraper("https://tiktok.com/@u/video/1"), TikTokScraper)
