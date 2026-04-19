# tests/conftest.py
import os
import pytest

# ── Layer 1: Set defaults at collection time ──────────────────────────
_TEST_DEFAULTS = {
    "TELEGRAM_TOKEN": "test-telegram-token",
    "ANTHROPIC_API_KEY": "test-anthropic-key",
    "SUPABASE_URL": "https://test.supabase.co",
    "SUPABASE_KEY": "test-supabase-key",
    "WHITELISTED_USER_IDS": "12345",
}
for key, val in _TEST_DEFAULTS.items():
    os.environ.setdefault(key, val)

# ── Layer 2: Per-test fixture for isolation ───────────────────────────


@pytest.fixture(autouse=True)
def _required_env_vars(monkeypatch):
    """Re-apply test defaults via monkeypatch so they auto-revert after each test."""
    for key, val in _TEST_DEFAULTS.items():
        monkeypatch.setenv(key, val)


# ── Layer 3: Integration test opt-in ─────────────────────────────────


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests that hit real external services",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-integration"):
        skip = pytest.mark.skip(reason="pass --run-integration to run")
        for item in items:
            if item.get_closest_marker("integration"):
                item.add_marker(skip)
