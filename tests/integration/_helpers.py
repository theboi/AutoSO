# tests/integration/_helpers.py
"""Shared helpers for integration tests. Safe to import from conftest and tests."""
from pathlib import Path
from dotenv import dotenv_values

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_PATH = _REPO_ROOT / ".env"

# Read .env once at import time using an explicit, CWD-independent path
DOTENV: dict[str, str | None] = dict(dotenv_values(_ENV_PATH))

# Placeholders defined in the root tests/conftest.py; we treat these as "not real"
_TEST_PLACEHOLDERS = {
    "test-telegram-token",
    "test-anthropic-key",
    "https://test.supabase.co",
    "test-supabase-key",
}


def is_real_credential(val: str | None) -> bool:
    """Return True if val looks like a real credential, not a test placeholder."""
    return bool(val) and val not in _TEST_PLACEHOLDERS and not val.startswith("your_")


# Modules whose globals we must patch because they cached env values at import time.
# Order matters: patch autoso.config first so downstream re-exports see the new value
# if they look it up dynamically.
_MODULES_TO_PATCH = [
    "autoso.config",
]
