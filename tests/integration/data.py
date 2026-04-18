# tests/integration/data.py
# Default URLs for live scraping tests — fill these in before running.
# Override at runtime by passing --url to the CLI, or by setting the variable
# directly in your test invocation.
from autoso.scraping.models import Comment, Post

REDDIT_URL: str = "https://www.reddit.com/r/Bolehland/comments/1sju0kx/malaysian_who_grew_up_in_singapore_as_pr_skipped/"      # e.g. https://www.reddit.com/r/singapore/comments/...
INSTAGRAM_URL: str = ""   # e.g. https://www.instagram.com/p/...
FACEBOOK_URL: str = "https://www.facebook.com/100064763316351/posts/1424578959710868/"    # e.g. https://www.facebook.com/mindef.sg/posts/...

# Canned post used by analyze tests — no scraping needed.
CANNED_POST = Post(
    title="Singapore NS Policy Discussion",
    content="Singapore introduces new National Service policy changes for 2024, "
            "including improvements to NSF allowances and vocational training.",
    url="https://www.reddit.com/r/singapore/comments/test",
    platform="reddit",
    comments=[
        Comment(platform="reddit", text="NS has been very beneficial for Singapore's defence. I'm proud to serve.", comment_id="c1", position=0),
        Comment(platform="reddit", text="The training is tough but it builds character and discipline in young men.", comment_id="c2", position=1),
        Comment(platform="reddit", text="I think MINDEF should improve the welfare of NSFs. The allowance is too low.", comment_id="c3", position=2),
        Comment(platform="reddit", text="NS is a necessary sacrifice for the country's security.", comment_id="c4", position=3),
        Comment(platform="reddit", text="The new policy changes are a step in the right direction for modernising our defence force.", comment_id="c5", position=4),
        Comment(platform="reddit", text="Some units are better run than others. Management quality varies a lot.", comment_id="c6", position=5),
        Comment(platform="reddit", text="NS teaches you time management and working with diverse groups of people.", comment_id="c7", position=6),
        Comment(platform="reddit", text="The government should consider the opportunity cost of 2 years for young Singaporeans.", comment_id="c8", position=7),
        Comment(platform="reddit", text="MINDEF has been doing a good job communicating policy changes through social media.", comment_id="c9", position=8),
        Comment(platform="reddit", text="The bilateral defence cooperation with regional partners is very important.", comment_id="c10", position=9),
    ],
)
