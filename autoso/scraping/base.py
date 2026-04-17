from urllib.parse import urlparse


def detect_platform(url: str) -> str:
    """Detect the social platform from a URL.

    Uses hostname matching (not substring-in-full-URL) to avoid false positives.
    """
    hostname = urlparse(url).hostname or ""
    # Strip leading "www." / "m." for uniform matching
    bare = hostname.removeprefix("www.").removeprefix("m.")

    if bare == "reddit.com" or bare.endswith(".reddit.com"):
        return "reddit"
    if bare == "instagram.com" or bare.endswith(".instagram.com"):
        return "instagram"
    if bare == "facebook.com" or bare.endswith(".facebook.com") or bare == "fb.com":
        return "facebook"
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
    raise ValueError(f"No scraper registered for platform: {platform}")
