# tests/integration/test_analyze.py
import os
from pathlib import Path
import pytest
from autoso.diagnostics.analyze import run
from tests.integration.data import CANNED_POST, FACEBOOK_URL
from tests.integration._helpers import is_real_credential

_SESSION_DIR = Path(__file__).resolve().parents[2] / "data" / "sessions"


def _require_anthropic() -> None:
    # Read from os.environ (monkeypatched, live) not autoso.config (frozen at import).
    if not is_real_credential(os.environ.get("ANTHROPIC_API_KEY")):
        pytest.skip("Real ANTHROPIC_API_KEY not configured in .env")


@pytest.mark.integration
def test_texture_analysis_returns_valid_format():
    _require_anthropic()

    result = run(CANNED_POST, "texture")

    assert result["ok"] is True, f"Analysis failed: {result.get('error')}"
    assert result.get("skipped") is not True
    assert result["title"] == CANNED_POST.title
    assert len(result["output"]) > 0
    # Texture format must contain percentage breakdowns
    assert "%" in result["output"], "Texture output missing percentage markers"


@pytest.mark.integration
def test_texture_facebook_live_scrape():
    """End-to-end: scrape the Facebook URL then run texture analysis on it."""
    if not FACEBOOK_URL:
        pytest.skip("FACEBOOK_URL not set in tests/integration/data.py")
    _require_anthropic()

    cookie_file = _SESSION_DIR / "facebook_session.json"
    if not cookie_file.exists():
        pytest.skip(
            f"No session cookies at {cookie_file}. "
            "Log in interactively and save cookies before running Facebook integration tests."
        )

    from autoso.scraping.base import get_scraper

    scraper = get_scraper(FACEBOOK_URL)
    post = scraper.scrape(FACEBOOK_URL)

    assert len(post.comments) > 0, "Facebook scraper returned 0 comments"

    result = run(post, "texture")

    assert result["ok"] is True, f"Texture analysis failed: {result.get('error')}"
    assert len(result["output"]) > 0
    assert "%" in result["output"], "Texture output missing percentage markers"


@pytest.mark.integration
def test_bucket_analysis_returns_valid_format_or_skips_if_no_holy_grail():
    _require_anthropic()

    result = run(CANNED_POST, "bucket")

    if result.get("skipped"):
        pytest.skip(result["reason"])

    assert result["ok"] is True, f"Analysis failed: {result.get('error')}"
    assert len(result["output"]) > 0
    # Bucket format must contain sentiment section headers
    output_lower = result["output"].lower()
    assert "positive" in output_lower or "negative" in output_lower, (
        "Bucket output missing expected sentiment sections (Positive/Negative)"
    )
