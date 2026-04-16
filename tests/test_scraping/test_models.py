from autoso.scraping.models import Comment, Post


def test_comment_construction():
    c = Comment(platform="reddit", text="Hello", comment_id="abc", position=0)
    assert c.platform == "reddit"
    assert c.text == "Hello"
    assert c.comment_id == "abc"
    assert c.position == 0


def test_post_construction():
    comments = [Comment(platform="reddit", text="hi", comment_id="c1", position=0)]
    post = Post(
        title="Test",
        content="Post body",
        url="https://reddit.com/r/test/comments/abc",
        platform="reddit",
        comments=comments,
    )
    assert post.platform == "reddit"
    assert len(post.comments) == 1
    assert post.comments[0].comment_id == "c1"


def test_post_comments_default_empty():
    post = Post(
        title="T", content="C", url="http://x.com", platform="reddit", comments=[]
    )
    assert post.comments == []
