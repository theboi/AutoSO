import praw
from autoso.scraping.models import Comment, Post
from autoso.config import REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT


class RedditScraper:
    def __init__(self):
        self._reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT,
            read_only=True,
        )

    def scrape(self, url: str, limit: int = 500) -> Post:
        submission = self._reddit.submission(url=url)
        submission.comments.replace_more(limit=0)

        comments = []
        for i, c in enumerate(submission.comments.list()[:limit]):
            if c.body.startswith("[deleted]") or c.body.startswith("[removed]"):
                continue
            comments.append(
                Comment(
                    platform="reddit",
                    text=c.body,
                    comment_id=c.id,
                    position=i,
                )
            )

        return Post(
            title=submission.title,
            content=submission.selftext or submission.title,
            url=url,
            platform="reddit",
            comments=comments,
        )
