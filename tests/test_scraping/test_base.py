import pytest
from autoso.scraping.base import detect_platform


def test_detect_reddit():
    assert detect_platform("https://www.reddit.com/r/singapore/comments/abc") == "reddit"


def test_detect_instagram():
    assert detect_platform("https://www.instagram.com/p/ABC123/") == "instagram"


def test_detect_instagram_no_www():
    assert detect_platform("https://instagram.com/p/ABC123/") == "instagram"


def test_detect_facebook_full():
    assert detect_platform("https://www.facebook.com/groups/123/posts/456") == "facebook"


def test_detect_facebook_mobile():
    assert detect_platform("https://m.facebook.com/story.php?id=123") == "facebook"


def test_detect_facebook_short():
    assert detect_platform("https://fb.com/story.php?id=123") == "facebook"


def test_detect_unsupported_raises():
    with pytest.raises(ValueError, match="Unsupported platform"):
        detect_platform("https://twitter.com/x/status/1")


def test_detect_does_not_false_positive_on_notfb_com():
    """'fb.com' substring in a different domain must not match Facebook."""
    with pytest.raises(ValueError, match="Unsupported platform"):
        detect_platform("https://notfb.com/page")


def test_detect_does_not_false_positive_on_subdomain_lookalike():
    """A domain that ends in a platform name but isn't one must not match."""
    with pytest.raises(ValueError, match="Unsupported platform"):
        detect_platform("https://notreddit.com/r/test")
