from urllib.parse import urlparse


def detect_platform(url: str) -> str:
    """Detect the social platform from a URL. Hostname-based matching."""
    hostname = urlparse(url).hostname or ""
    bare = hostname.removeprefix("www.").removeprefix("m.")

    if bare == "reddit.com" or bare.endswith(".reddit.com"):
        return "reddit"
    if bare == "instagram.com" or bare.endswith(".instagram.com"):
        return "instagram"
    if bare == "facebook.com" or bare.endswith(".facebook.com") or bare == "fb.com":
        return "facebook"
    if bare == "hardwarezone.com.sg" or bare.endswith(".hardwarezone.com.sg"):
        return "hardwarezone"
    if bare == "youtube.com" or bare.endswith(".youtube.com") or bare == "youtu.be":
        return "youtube"
    if bare == "tiktok.com" or bare.endswith(".tiktok.com"):
        return "tiktok"
    raise ValueError(f"Unsupported platform for URL: {url}")


def get_scraper(url: str):
    """Return the appropriate scraper instance for the given URL."""
    platform = detect_platform(url)
    if platform == "reddit":
        from autoso.scraping.reddit import RedditScraper
        return RedditScraper()
    if platform == "instagram":
        from autoso.scraping.instagram import InstagramScraper
        return InstagramScraper()
    if platform == "facebook":
        from autoso.scraping.facebook import FacebookScraper
        return FacebookScraper()
    if platform == "hardwarezone":
        from autoso.scraping.hardwarezone import HardwareZoneScraper
        return HardwareZoneScraper()
    if platform == "youtube":
        from autoso.scraping.youtube import YouTubeScraper
        return YouTubeScraper()
    if platform == "tiktok":
        from autoso.scraping.tiktok import TikTokScraper
        return TikTokScraper()
    raise ValueError(f"No scraper registered for platform: {platform}")
