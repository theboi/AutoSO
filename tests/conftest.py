# tests/conftest.py
import os

# ── Layer 1: Set defaults at collection time ──────────────────────────
_TEST_DEFAULTS = {
    "TELEGRAM_TOKEN": "test-telegram-token",
    "ANTHROPIC_API_KEY": "test-anthropic-key",
    "SUPABASE_URL": "https://test.supabase.co",
    "SUPABASE_KEY": "test-supabase-key",
    "REDDIT_CLIENT_ID": "test-reddit-client-id",
    "REDDIT_CLIENT_SECRET": "test-reddit-secret",
    "REDDIT_USER_AGENT": "AutoSO/test",
    "WHITELISTED_USER_IDS": "12345",
}
for key, val in _TEST_DEFAULTS.items():
    os.environ.setdefault(key, val)

# ── Layer 2: Per-test fixture for isolation ───────────────────────────
import pytest


@pytest.fixture(autouse=True)
def _required_env_vars(monkeypatch):
    """Re-apply test defaults via monkeypatch so they auto-revert after each test."""
    for key, val in _TEST_DEFAULTS.items():
        monkeypatch.setenv(key, val)
