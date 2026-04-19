# autoso/diagnostics/scrape.py
"""Verify that a live URL can be scraped and returns non-zero comments.

Usage:
    python -m autoso.diagnostics.scrape --url https://www.reddit.com/r/singapore/...

Platform is auto-detected from the URL.
"""
import argparse
import json
import sys


def run(url: str, platform: str) -> dict:
    """Scrape url and return a result dict.

    Returns:
        {"ok": True, "platform": ..., "url": ..., "comment_count": N, "title": ..., "comments": [...]}
        {"ok": False, "platform": ..., "url": ..., "error": "..."}
    """
    from autoso.scraping.base import get_scraper
    from autoso.scraping import flatten_comments, scrape
    from autoso.storage.supabase import store_scrape

    try:
        scraper = get_scraper(url)
        post = scraper.scrape(url)
        scrape_id = store_scrape(url, post)
    except Exception as exc:
        return {"ok": False, "platform": platform, "url": url, "error": str(exc)}

    all_comments = flatten_comments(post)
    ok = len(all_comments) > 0
    return {
        "ok": ok,
        "platform": platform,
        "url": url,
        "scrape_id": scrape_id,
        "comment_count": len(all_comments),
        "title": post.post_title,
        "comments": [c.text for c in all_comments],
        **({"error": "zero comments returned"} if not ok else {}),
    }


if __name__ == "__main__":
    from autoso.scraping.base import detect_platform

    parser = argparse.ArgumentParser(description="Live scraping diagnostic")
    parser.add_argument("--url", required=True, help="URL to scrape (platform is auto-detected)")
    args = parser.parse_args()

    try:
        platform = detect_platform(args.url)
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    result = run(args.url, platform)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)
