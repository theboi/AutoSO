from autoso.scraping.base import get_scraper
from autoso.scraping.models import Comment, Post
from autoso.storage.supabase import get_recent_scrape, store_scrape


def scrape(url: str) -> tuple[str, Post]:
    """Scrape URL, returning (scrape_id, Post) with cache support."""
    cached = get_recent_scrape(url)
    if cached is not None:
        return cached

    scraper = get_scraper(url)
    post = scraper.scrape(url)
    scrape_id = store_scrape(url, post)
    return scrape_id, post


def flatten_comments(post: Post) -> list[Comment]:
    """Return all comments/subcomments depth-first."""
    out: list[Comment] = []
    for comment in post.comments:
        _walk(comment, out)
    return out


def _walk(comment: Comment, out: list[Comment]) -> None:
    out.append(comment)
    for subcomment in comment.subcomments:
        _walk(subcomment, out)
