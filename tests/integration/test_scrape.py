# tests/integration/test_scrape.py
import os
from pathlib import Path
import pytest

from autoso.diagnostics.scrape import run
from tests.integration.data import REDDIT_URL, INSTAGRAM_URL, FACEBOOK_URL
from tests.integration._helpers import is_real_credential

_SESSION_DIR = Path(__file__).resolve().parents[2] / "data" / "sessions"


def _require_env(*names: str) -> None:
    """Skip if any env var is missing or still a test placeholder."""
    for name in names:
        if not is_real_credential(os.environ.get(name)):
            pytest.skip(f"Real {name} not configured in .env")


def _require_session_cookies(platform: str) -> None:
    cookie_file = _SESSION_DIR / f"{platform}_session.json"
    if not cookie_file.exists():
        pytest.skip(
            f"No session cookies at {cookie_file}. "
            f"Log in interactively and save cookies before running {platform} integration tests."
        )


@pytest.mark.integration
def test_reddit_scrape_returns_comments():
    if not REDDIT_URL:
        pytest.skip("REDDIT_URL not set in tests/integration/data.py")

    result = run(REDDIT_URL, "reddit")

    assert result["ok"] is True, f"Scrape failed: {result.get('error')}"
    assert result["comment_count"] > 0
    assert result["platform"] == "reddit"


@pytest.mark.integration
def test_instagram_scrape_returns_comments():
    if not INSTAGRAM_URL:
        pytest.skip("INSTAGRAM_URL not set in tests/integration/data.py")
    _require_session_cookies("instagram")

    result = run(INSTAGRAM_URL, "instagram")

    assert result["ok"] is True, f"Scrape failed: {result.get('error')}"
    assert result["comment_count"] > 0
    assert result["platform"] == "instagram"


@pytest.mark.integration
def test_facebook_scrape_returns_comments():
    if not FACEBOOK_URL:
        pytest.skip("FACEBOOK_URL not set in tests/integration/data.py")
    _require_session_cookies("facebook")

    result = run(FACEBOOK_URL, "facebook")

    assert result["ok"] is True, f"Scrape failed: {result.get('error')}"
    assert result["comment_count"] > 0
    assert result["platform"] == "facebook"
