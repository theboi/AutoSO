# tests/integration/data.py
# ─────────────────────────────────────────────────────────────────────────────
# INPUT ALL TEST URLS HERE — one per platform.
# Run a single platform:  python -m autoso.diagnostics.scrape --url <URL>
# Run all platforms:      python tests/integration/run_all.py
# ─────────────────────────────────────────────────────────────────────────────
from autoso.scraping.models import Comment, Post

# Reddit — requires PROXY_URL (residential/ISP) or run from a non-datacenter IP
REDDIT_URL: str = "https://www.reddit.com/r/Bolehland/comments/1sju0kx/malaysian_who_grew_up_in_singapore_as_pr_skipped/"

# Instagram — requires data/sessions/instagram_session.json (run login helper)
INSTAGRAM_URL: str = "https://www.instagram.com/p/DXEA8iQj5YY/"

# Facebook — requires data/sessions/facebook_session.json (already configured)
FACEBOOK_URL: str = "https://www.facebook.com/100064763316351/posts/1424578959710868/"

# TikTok — session required; run: python scripts/save_session.py tiktok
TIKTOK_URL: str = "https://www.tiktok.com/@mindefsg/video/7449298784200212486"

# YouTube — no auth on residential IPs; on cloud IPs set YOUTUBE_COOKIES_FILE in .env
YOUTUBE_URL: str = "https://www.youtube.com/watch?v=AXOhIZURyMY"

# HardwareZone — no auth needed
HARDWAREZONE_URL: str = "https://forums.hardwarezone.com.sg/threads/the-smart-home-tech-show-2026-x-hwz-giveaway-labour-day-special.7199663/"

# Canned post used by analyze tests — no scraping needed.
CANNED_POST = Post(
    id="itest_post",
    platform="reddit",
    url="https://www.reddit.com/r/singapore/comments/test",
    page_title="r/singapore",
    post_title="Singapore NS Policy Discussion",
    date=None,
    author=None,
    content="Singapore introduces new National Service policy changes for 2024, "
            "including improvements to NSF allowances and vocational training.",
    likes=None,
    comments=[
        Comment(id="c1", platform="reddit", author=None, date=None, text="NS has been very beneficial for Singapore's defence. I'm proud to serve.", likes=None, position=0),
        Comment(id="c2", platform="reddit", author=None, date=None, text="The training is tough but it builds character and discipline in young men.", likes=None, position=1),
        Comment(id="c3", platform="reddit", author=None, date=None, text="I think MINDEF should improve the welfare of NSFs. The allowance is too low.", likes=None, position=2),
        Comment(id="c4", platform="reddit", author=None, date=None, text="NS is a necessary sacrifice for the country's security.", likes=None, position=3),
        Comment(id="c5", platform="reddit", author=None, date=None, text="The new policy changes are a step in the right direction for modernising our defence force.", likes=None, position=4),
        Comment(id="c6", platform="reddit", author=None, date=None, text="Some units are better run than others. Management quality varies a lot.", likes=None, position=5),
        Comment(id="c7", platform="reddit", author=None, date=None, text="NS teaches you time management and working with diverse groups of people.", likes=None, position=6),
        Comment(id="c8", platform="reddit", author=None, date=None, text="The government should consider the opportunity cost of 2 years for young Singaporeans.", likes=None, position=7),
        Comment(id="c9", platform="reddit", author=None, date=None, text="MINDEF has been doing a good job communicating policy changes through social media.", likes=None, position=8),
        Comment(id="c10", platform="reddit", author=None, date=None, text="The bilateral defence cooperation with regional partners is very important.", likes=None, position=9),
    ],
)
