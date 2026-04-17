# Integration Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `autoso/diagnostics/` package with three runnable modules (scrape, analyze, telegram) that verify live external integrations, exposed both as `python -m autoso.diagnostics.<name>` CLI tools and as `pytest --run-integration` test suites.

**Architecture:** Diagnostic logic lives in `autoso/diagnostics/` (production code, no test dependencies). `tests/integration/` contains thin pytest wrappers that import from diagnostics and provide default test data. Tests are skipped by default; opt in with `--run-integration`. Tests also auto-skip if required real credentials aren't present in `.env`.

**Tech Stack:** pytest, python-telegram-bot, existing autoso pipeline/scraping modules, dotenv

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Modify | `pyproject.toml` | Register `integration` pytest marker |
| Modify | `tests/conftest.py` | Add `--run-integration` flag + skip hook |
| Create | `tests/integration/__init__.py` | Package marker |
| Create | `tests/integration/_helpers.py` | `is_real_credential`, placeholder set, `.env` path loader |
| Create | `tests/integration/conftest.py` | Override test creds with real `.env` values in `os.environ` AND in `autoso.config` / `autoso.scraping.reddit` module globals; reset LLM singleton |
| Create | `tests/integration/data.py` | Default URLs (user fills in) + `CANNED_POST` |
| Create | `autoso/diagnostics/__init__.py` | Package marker |
| Create | `autoso/diagnostics/scrape.py` | `run(url, platform) -> dict` + `__main__` (required `--url`) |
| Create | `autoso/diagnostics/analyze.py` | `run(post, mode) -> dict` + `__main__` |
| Create | `autoso/diagnostics/telegram.py` | `run() -> dict` + `__main__` |
| Create | `tests/integration/test_scrape.py` | 3 integration tests (one per platform; IG/FB guarded by session-cookie file) |
| Create | `tests/integration/test_analyze.py` | 2 integration tests (texture + bucket) |
| Create | `tests/integration/test_telegram.py` | 1 integration test (getMe) |

**Why the patching is necessary:** `autoso/config.py` reads env vars at module-import time (`TELEGRAM_TOKEN: str = os.environ["TELEGRAM_TOKEN"]`). The root `conftest.py` sets placeholder env vars before `autoso.config` is first imported, so the placeholders are permanently baked into `autoso.config.*` attributes and into any module that did `from autoso.config import X`. `monkeypatch.setenv` alone is insufficient — integration conftest must also `monkeypatch.setattr` the module globals. It must also reset `autoso.pipeline.llm._configured` so `configure_llm()` rebuilds `Settings.llm` with the real API key instead of the cached placeholder-keyed one.

---

## Task 1: pytest infrastructure

**Files:**
- Modify: `pyproject.toml`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add `integration` marker to pyproject.toml**

In `pyproject.toml`, replace the `[tool.pytest.ini_options]` section:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = [
    "integration: marks tests as integration tests that hit real external services (opt-in with --run-integration)",
]
```

- [ ] **Step 2: Add `--run-integration` CLI flag and skip hook to `tests/conftest.py`**

Replace the full contents of `tests/conftest.py`:

```python
# tests/conftest.py
import os
import pytest

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
```

- [ ] **Step 3: Verify unit tests still pass**

```bash
pytest tests/ -m "not integration" -q
```

Expected: all existing unit tests pass, no new failures.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml tests/conftest.py
git commit -m "test: add --run-integration flag and integration marker"
```

---

## Task 2: Integration test data file

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/data.py`

- [ ] **Step 1: Create package marker**

Create `tests/integration/__init__.py` as an empty file.

- [ ] **Step 2: Create `tests/integration/data.py`**

```python
# tests/integration/data.py
# Default URLs for live scraping tests — fill these in before running.
# Override at runtime by passing --url to the CLI, or by setting the variable
# directly in your test invocation.
from autoso.scraping.models import Comment, Post

REDDIT_URL: str = ""      # e.g. https://www.reddit.com/r/singapore/comments/...
INSTAGRAM_URL: str = ""   # e.g. https://www.instagram.com/p/...
FACEBOOK_URL: str = ""    # e.g. https://www.facebook.com/mindef.sg/posts/...

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
```

- [ ] **Step 3: Commit**

```bash
git add tests/integration/__init__.py tests/integration/data.py
git commit -m "test: add integration test data file with placeholder URLs and canned post"
```

---

## Task 3: Integration helpers + conftest — real credential override

**Files:**
- Create: `tests/integration/_helpers.py`
- Create: `tests/integration/conftest.py`

**Why two files:** Tests need to import `is_real_credential` to decide whether to skip. Importing from `conftest.py` is fragile (pytest doesn't guarantee it's importable as a module). We put the helper in `_helpers.py` and import it from both conftest and the test files.

**Why we patch module attributes and not just env vars:** `autoso/config.py` does `TELEGRAM_TOKEN: str = os.environ["TELEGRAM_TOKEN"]` at module import time. By the time the integration fixture runs, `autoso.config.TELEGRAM_TOKEN` is already bound to the placeholder `"test-telegram-token"`. Same for `autoso/scraping/reddit.py` which re-exports via `from autoso.config import REDDIT_CLIENT_ID, ...`. We need `monkeypatch.setattr` on those module attributes, not just `setenv`.

**Why we reset `_configured`:** `autoso.pipeline.llm` caches `Settings.llm` in a singleton. If any prior unit test called `configure_llm()` with the placeholder API key, integration tests inherit a broken LLM client.

- [ ] **Step 1: Create `tests/integration/_helpers.py`**

```python
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
    "test-reddit-client-id",
    "test-reddit-secret",
    "AutoSO/test",
}


def is_real_credential(val: str | None) -> bool:
    """Return True if val looks like a real credential, not a test placeholder."""
    return bool(val) and val not in _TEST_PLACEHOLDERS and not val.startswith("your_")


# Modules whose globals we must patch because they cached env values at import time.
# Order matters: patch autoso.config first so downstream re-exports see the new value
# if they look it up dynamically.
_MODULES_TO_PATCH = [
    "autoso.config",
    "autoso.scraping.reddit",  # does `from autoso.config import REDDIT_CLIENT_ID, ...`
]
```

- [ ] **Step 2: Create `tests/integration/conftest.py`**

```python
# tests/integration/conftest.py
import importlib
import pytest

from tests.integration._helpers import DOTENV, is_real_credential, _MODULES_TO_PATCH


@pytest.fixture(autouse=True)
def _use_real_env(monkeypatch):
    """Replace test-placeholder env vars with real .env values for integration tests.

    This runs after the root conftest's _required_env_vars fixture. Because
    autoso.config and some downstream modules captured env values at import time,
    we patch both os.environ (via setenv) AND the already-imported module globals
    (via setattr).
    """
    # 1. Patch os.environ — safe baseline, reverts after each test.
    for key, val in DOTENV.items():
        if is_real_credential(val):
            monkeypatch.setenv(key, val)

    # 2. Patch already-imported module globals that captured placeholders.
    for mod_name in _MODULES_TO_PATCH:
        try:
            mod = importlib.import_module(mod_name)
        except Exception:
            continue
        for key, val in DOTENV.items():
            if is_real_credential(val) and hasattr(mod, key):
                monkeypatch.setattr(mod, key, val)

    # 3. Reset autoso.pipeline.llm singleton. The next configure_llm() call will
    #    reassign Settings.llm with the real ANTHROPIC_API_KEY.
    try:
        llm_mod = importlib.import_module("autoso.pipeline.llm")
        monkeypatch.setattr(llm_mod, "_configured", False)
    except Exception:
        pass
```

- [ ] **Step 3: Verify unit tests are unaffected**

```bash
pytest tests/ -m "not integration" -q
```

Expected: same results as before — no failures, no extra skips.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/_helpers.py tests/integration/conftest.py
git commit -m "test: integration conftest overrides test creds with real .env values"
```

---

## Task 4: `autoso/diagnostics/scrape.py`

**Files:**
- Create: `autoso/diagnostics/__init__.py`
- Create: `autoso/diagnostics/scrape.py`

- [ ] **Step 1: Create package marker**

Create `autoso/diagnostics/__init__.py` as an empty file.

- [ ] **Step 2: Create `autoso/diagnostics/scrape.py`**

```python
# autoso/diagnostics/scrape.py
"""Verify that a live URL can be scraped and returns non-zero comments.

Usage:
    python -m autoso.diagnostics.scrape --url https://www.reddit.com/r/singapore/...

Platform is auto-detected from the URL.
"""
import argparse
import json
import sys


def run(url: str, platform: str) -> dict:
    """Scrape url and return a result dict.

    Returns:
        {"ok": True, "platform": ..., "url": ..., "comment_count": N, "title": ...}
        {"ok": False, "platform": ..., "url": ..., "error": "..."}
    """
    from autoso.scraping.base import get_scraper

    try:
        scraper = get_scraper(url)
        post = scraper.scrape(url)
    except Exception as exc:
        return {"ok": False, "platform": platform, "url": url, "error": str(exc)}

    ok = len(post.comments) > 0
    return {
        "ok": ok,
        "platform": platform,
        "url": url,
        "comment_count": len(post.comments),
        "title": post.title,
        **({"error": "zero comments returned"} if not ok else {}),
    }


if __name__ == "__main__":
    from autoso.scraping.base import detect_platform

    parser = argparse.ArgumentParser(description="Live scraping diagnostic")
    parser.add_argument("--url", required=True, help="URL to scrape (platform is auto-detected)")
    args = parser.parse_args()

    try:
        platform = detect_platform(args.url)
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    result = run(args.url, platform)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)
```

**Note:** Default URLs for *tests* still live in `tests/integration/data.py`. The CLI no longer reaches into test code; it now requires `--url`.

- [ ] **Step 3: Smoke-test the CLI (read-only check, no network)**

```bash
python -m autoso.diagnostics.scrape --help
```

Expected: prints usage without error.

- [ ] **Step 4: Commit**

```bash
git add autoso/diagnostics/__init__.py autoso/diagnostics/scrape.py
git commit -m "feat: add diagnostics/scrape module for live scraping verification"
```

---

## Task 5: `tests/integration/test_scrape.py`

**Files:**
- Create: `tests/integration/test_scrape.py`

- [ ] **Step 1: Create `tests/integration/test_scrape.py`**

Skip-check notes:
- Credential check reads from `os.environ` (the live, monkeypatched value), NOT from `autoso.config` (frozen at import time).
- Instagram/Facebook require Playwright session cookies at `data/sessions/{platform}_session.json`. If missing, the scraper will hit a login wall and raise `ScrapeError`. We skip preemptively so that a missing cookie file is a skip, not a failure.

```python
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
    _require_env("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET")

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
```

- [ ] **Step 2: Verify the tests are collected but skipped without the flag**

```bash
pytest tests/integration/test_scrape.py -v
```

Expected: all 3 tests show `SKIPPED` with reason "pass --run-integration to run".

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_scrape.py
git commit -m "test: add integration tests for live scraping (reddit/instagram/facebook)"
```

---

## Task 6: `autoso/diagnostics/analyze.py`

**Files:**
- Create: `autoso/diagnostics/analyze.py`

This module runs the LLM analysis pipeline on a provided `Post` without scraping or writing to Supabase. For bucket mode it gracefully skips if the Holy Grail hasn't been ingested.

- [ ] **Step 1: Create `autoso/diagnostics/analyze.py`**

```python
# autoso/diagnostics/analyze.py
"""Verify that the LLM analysis pipeline produces valid texture/bucket output.

Usage:
    python -m autoso.diagnostics.analyze --mode texture
    python -m autoso.diagnostics.analyze --mode bucket
"""
import argparse
import json
import sys
from typing import Literal

from autoso.scraping.models import Comment, Post

# Inline canned post for CLI use (tests use the richer one from tests/integration/data.py)
_CLI_CANNED_POST = Post(
    title="Singapore NS Policy Discussion",
    content="Singapore introduces new National Service policy changes for 2024.",
    url="https://www.reddit.com/r/singapore/comments/cli_test",
    platform="reddit",
    comments=[
        Comment(platform="reddit", text="NS has been very beneficial for Singapore's defence.", comment_id="c1", position=0),
        Comment(platform="reddit", text="The training builds character and discipline in young men.", comment_id="c2", position=1),
        Comment(platform="reddit", text="MINDEF should improve NSF allowances — the pay is too low.", comment_id="c3", position=2),
        Comment(platform="reddit", text="NS is a necessary sacrifice for the country's security.", comment_id="c4", position=3),
        Comment(platform="reddit", text="The new policy changes modernise our defence force.", comment_id="c5", position=4),
        Comment(platform="reddit", text="Management quality varies a lot across different units.", comment_id="c6", position=5),
        Comment(platform="reddit", text="NS teaches time management and teamwork.", comment_id="c7", position=6),
        Comment(platform="reddit", text="Consider the opportunity cost of 2 years for young Singaporeans.", comment_id="c8", position=7),
    ],
)


def run(post: Post, mode: Literal["texture", "bucket"]) -> dict:
    """Run LLM analysis on post and return a result dict.

    Skips (ok=True, skipped=True) for bucket mode if Holy Grail is not ingested.

    Returns:
        {"ok": True, "mode": ..., "title": ..., "output": ..., "citation_count": N}
        {"ok": True, "skipped": True, "reason": "..."}   # bucket without holy grail
        {"ok": False, "mode": ..., "error": "..."}
    """
    from autoso.pipeline.citation import build_citation_engine, extract_citations, strip_citation_markers
    from autoso.pipeline.indexer import index_comments
    from autoso.pipeline.llm import configure_llm
    from autoso.pipeline.prompts import (
        BUCKET_FORMAT_INSTRUCTION,
        BUCKET_SYSTEM_PROMPT,
        TEXTURE_FORMAT_INSTRUCTION,
        TEXTURE_SYSTEM_PROMPT,
    )

    try:
        configure_llm()
        comment_index = index_comments(post.comments)

        comments_text = "\n".join(f"Comment {c.position}: {c.text}" for c in post.comments)
        post_context = (
            f"{post.platform.upper()} POST:\n{post.content}\n\n"
            f"COMMENTS:\n{comments_text}"
        )

        if mode == "texture":
            system = TEXTURE_SYSTEM_PROMPT
            full_query = f"{post_context}\n\n{TEXTURE_FORMAT_INSTRUCTION.format(title=post.title)}"

        elif mode == "bucket":
            from autoso.pipeline.holy_grail import load_holy_grail
            try:
                holy_grail_index = load_holy_grail()
            except RuntimeError:
                return {
                    "ok": True,
                    "skipped": True,
                    "reason": "Holy Grail not ingested — run: python scripts/ingest_holy_grail.py <path>",
                }
            system = BUCKET_SYSTEM_PROMPT
            hg_engine = build_citation_engine(holy_grail_index, similarity_top_k=20)
            hg_response = hg_engine.query(
                "List all bucket labels for MINDEF/SAF/NS/Defence sentiment analysis"
            )
            full_query = (
                f"{post_context}\n\n"
                f"BUCKET HOLY GRAIL REFERENCE:\n{hg_response}\n\n"
                f"{BUCKET_FORMAT_INSTRUCTION.format(title=post.title)}"
            )
        else:
            return {"ok": False, "mode": mode, "error": f"unknown mode: {mode!r}"}

        engine = build_citation_engine(comment_index, system_prompt=system)
        response = engine.query(full_query)
        output_cited = str(response)
        output_clean = strip_citation_markers(output_cited)
        citations = extract_citations(response)

        return {
            "ok": True,
            "mode": mode,
            "title": post.title,
            "output": output_clean,
            "citation_count": len(citations),
        }

    except Exception as exc:
        return {"ok": False, "mode": mode, "error": str(exc)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live LLM analysis diagnostic")
    parser.add_argument("--mode", choices=["texture", "bucket"], default="texture")
    args = parser.parse_args()

    result = run(_CLI_CANNED_POST, args.mode)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)
```

- [ ] **Step 2: Smoke-test the CLI**

```bash
python -m autoso.diagnostics.analyze --help
```

Expected: prints usage without error.

- [ ] **Step 3: Commit**

```bash
git add autoso/diagnostics/analyze.py
git commit -m "feat: add diagnostics/analyze module for live LLM pipeline verification"
```

---

## Task 7: `tests/integration/test_analyze.py`

**Files:**
- Create: `tests/integration/test_analyze.py`

Format assertions are intentionally loose — they catch structural regressions without being brittle to exact LLM phrasing.

- [ ] **Step 1: Create `tests/integration/test_analyze.py`**

```python
# tests/integration/test_analyze.py
import os
import pytest
from autoso.diagnostics.analyze import run
from tests.integration.data import CANNED_POST
from tests.integration._helpers import is_real_credential


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
```

- [ ] **Step 2: Verify skipped without flag**

```bash
pytest tests/integration/test_analyze.py -v
```

Expected: both tests show `SKIPPED`.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_analyze.py
git commit -m "test: add integration tests for LLM texture and bucket analysis"
```

---

## Task 8: `autoso/diagnostics/telegram.py`

**Files:**
- Create: `autoso/diagnostics/telegram.py`

- [ ] **Step 1: Create `autoso/diagnostics/telegram.py`**

```python
# autoso/diagnostics/telegram.py
"""Verify that the Telegram bot token is valid by calling getMe().

Usage:
    python -m autoso.diagnostics.telegram
"""
import json
import sys


def run() -> dict:
    """Call Telegram getMe() and return a result dict.

    Returns:
        {"ok": True, "username": "...", "id": N, "first_name": "..."}
        {"ok": False, "error": "..."}
    """
    import asyncio
    from telegram import Bot
    import autoso.config as config

    async def _get_me():
        async with Bot(token=config.TELEGRAM_TOKEN) as bot:
            return await bot.get_me()

    try:
        me = asyncio.run(_get_me())
        return {
            "ok": True,
            "username": me.username,
            "id": me.id,
            "first_name": me.first_name,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)
```

- [ ] **Step 2: Smoke-test that the module imports cleanly**

```bash
python -c "from autoso.diagnostics import telegram; print('ok')"
```

Expected: prints `ok` with no ImportError. (Running the CLI itself would attempt a real `getMe()` with the placeholder env `TELEGRAM_TOKEN` and fail — that's expected behavior and is exercised in Task 9 against real creds.)

- [ ] **Step 3: Commit**

```bash
git add autoso/diagnostics/telegram.py
git commit -m "feat: add diagnostics/telegram module for bot token verification"
```

---

## Task 9: `tests/integration/test_telegram.py`

**Files:**
- Create: `tests/integration/test_telegram.py`

- [ ] **Step 1: Create `tests/integration/test_telegram.py`**

```python
# tests/integration/test_telegram.py
import os
import pytest
from autoso.diagnostics.telegram import run
from tests.integration._helpers import is_real_credential


@pytest.mark.integration
def test_telegram_bot_responds_to_get_me():
    # Read from os.environ (live, monkeypatched). autoso.config.TELEGRAM_TOKEN is
    # frozen to the test placeholder at module import time and cannot be used here.
    if not is_real_credential(os.environ.get("TELEGRAM_TOKEN")):
        pytest.skip("Real TELEGRAM_TOKEN not configured in .env")

    result = run()

    assert result["ok"] is True, f"Telegram getMe failed: {result.get('error')}"
    assert result["username"], "Bot username should be non-empty"
    assert isinstance(result["id"], int)
```

- [ ] **Step 2: Verify skipped without flag**

```bash
pytest tests/integration/test_telegram.py -v
```

Expected: `SKIPPED`.

- [ ] **Step 3: Verify all integration tests are skipped by default**

```bash
pytest tests/ -q
```

Expected: all integration tests skipped, all unit tests pass, zero failures.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_telegram.py
git commit -m "test: add integration test for Telegram bot liveness check"
```

---

## Verification

### Unit tests unaffected
```bash
pytest tests/ -m "not integration" -q
```
Expected: same results as before this feature.

### Integration tests skipped by default
```bash
pytest tests/ -q 2>&1 | grep -E "passed|skipped|failed"
```
Expected: integration tests appear as skipped, zero failures.

### CLI tools import cleanly
```bash
python -m autoso.diagnostics.scrape --help
python -m autoso.diagnostics.analyze --help
python -c "from autoso.diagnostics import telegram; print('ok')"
```
Expected: scrape/analyze print usage; telegram import prints `ok`. No ImportError anywhere.

### Live run (requires real creds in `.env` + filled-in URLs in `tests/integration/data.py`)
```bash
# Fill in tests/integration/data.py with real URLs first, then:
pytest tests/integration/ --run-integration -v

# Or run individually via CLI (must be invoked with REAL creds in .env — no test placeholders):
python -m autoso.diagnostics.scrape --url https://www.reddit.com/r/singapore/comments/...
python -m autoso.diagnostics.analyze --mode texture
python -m autoso.diagnostics.telegram
```

**Sanity check the fix worked:** With real creds in `.env` and at least `REDDIT_URL` filled in, `pytest tests/integration/test_scrape.py::test_reddit_scrape_returns_comments --run-integration -v` should show `PASSED` (not `SKIPPED`). If it shows `SKIPPED` with reason "Real REDDIT_CLIENT_ID not configured", the module-attribute patching in `tests/integration/conftest.py` is not taking effect — investigate fixture ordering before continuing.
