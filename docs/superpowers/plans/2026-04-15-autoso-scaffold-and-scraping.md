# AutoSO — Scaffold + Phase 1a (Scraping) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bootstrap the AutoSO project with a working Telegram bot scaffold, whitelist auth, and a reliable scraping layer for Reddit, Instagram, and Facebook.

**Architecture:** Python package under `autoso/`, flat layout. Scrapers share a common `Post`/`Comment` model. Reddit uses PRAW (official API). IG/FB use Playwright + playwright-stealth with persistent cookie sessions and human-like delays. A factory function `get_scraper(url)` routes by URL.

**Tech Stack:** Python 3.11+, python-telegram-bot 21+, PRAW, Playwright, playwright-stealth, pytest, pytest-asyncio, python-dotenv

---

## File Map

| File | Responsibility |
|------|---------------|
| `pyproject.toml` | Project metadata, dependencies, pytest config |
| `.env.example` | All required env var keys with placeholder values |
| `autoso/__init__.py` | Empty package marker |
| `autoso/config.py` | Load env vars into typed module-level constants |
| `autoso/bot/__init__.py` | Empty |
| `autoso/bot/auth.py` | `require_auth` decorator — whitelist check |
| `autoso/bot/handlers.py` | `/start`, `/texture`, `/bucket` stub handlers |
| `autoso/bot/main.py` | Application entry point — builds and runs the bot |
| `autoso/scraping/__init__.py` | Empty |
| `autoso/scraping/models.py` | `Comment` and `Post` dataclasses |
| `autoso/scraping/base.py` | `detect_platform(url)` and `get_scraper(url)` factory |
| `autoso/scraping/reddit.py` | `RedditScraper` using PRAW |
| `autoso/scraping/playwright_base.py` | `PlaywrightScraper` — session management, human delays |
| `autoso/scraping/instagram.py` | `InstagramScraper` extending `PlaywrightScraper` |
| `autoso/scraping/facebook.py` | `FacebookScraper` extending `PlaywrightScraper` |
| `tests/conftest.py` | Shared pytest fixtures — patches required env vars so tests never KeyError on import |
| `tests/test_auth.py` | Auth decorator unit tests |
| `tests/test_scraping/__init__.py` | Empty |
| `tests/test_scraping/test_models.py` | `Post`/`Comment` construction tests |
| `tests/test_scraping/test_base.py` | `detect_platform` and factory routing tests |
| `tests/test_scraping/test_reddit.py` | `RedditScraper` with mocked PRAW |
| `tests/test_scraping/test_instagram.py` | `InstagramScraper` with mocked Playwright |
| `tests/test_scraping/test_facebook.py` | `FacebookScraper` with mocked Playwright |
| `data/.gitkeep` | Ensures `data/` directory is tracked (chromadb + sessions live here) |

---

## Task 1: Project Skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `data/.gitkeep`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "autoso"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "python-telegram-bot>=21.0",
    "anthropic>=0.40.0",
    "llama-index-core>=0.12.46",
    "llama-index-llms-anthropic>=0.7.6",
    "llama-index-llms-ollama>=0.4.0",
    "llama-index-vector-stores-chroma>=0.4.0",
    "chromadb>=0.6.0",
    "praw>=7.7.0",
    "playwright>=1.40.0",
    "playwright-stealth>=1.0.6",
    "supabase>=2.3.0",
    "python-dotenv>=1.0.0",
    "openai-whisper>=20231117",
    "yt-dlp>=2024.1.0",
    "python-docx>=1.1.0",
    "fastapi>=0.109.0",
    "uvicorn>=0.27.0",
    "jinja2>=3.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-mock>=3.12.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create `.env.example`**

```bash
# Telegram
TELEGRAM_TOKEN=your_telegram_bot_token_here

# Anthropic
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key_here

# Reddit (PRAW)
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
REDDIT_USER_AGENT=AutoSO/1.0 by u/your_username

# Whitelist (comma-separated Telegram user IDs)
WHITELISTED_USER_IDS=123456789,987654321

# ChromaDB
CHROMADB_PATH=./data/chromadb

# LLM mode
# Set USE_OLLAMA=true for local dev (no API credits)
USE_OLLAMA=false
OLLAMA_MODEL=llama3.2
CLAUDE_MODEL=claude-sonnet-4-6
```

- [ ] **Step 3: Create `data/.gitkeep`**

```bash
touch data/.gitkeep
```

- [ ] **Step 4: Install dependencies**

```bash
pip install -e ".[dev]"
playwright install chromium
```

Expected: All packages install without error.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .env.example data/.gitkeep
git commit -m "chore: initialise project skeleton"
```

---

## Task 2: Config Module

**Files:**
- Create: `autoso/__init__.py`
- Create: `autoso/config.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create `autoso/__init__.py`**

Empty file.

```bash
mkdir -p autoso
touch autoso/__init__.py
```

- [ ] **Step 1b: Create `tests/conftest.py`**

All tests share this fixture. It patches the required env vars at session scope so importing any `autoso.*` module never raises `KeyError` in CI or a fresh checkout.

```python
# tests/conftest.py
import pytest


@pytest.fixture(autouse=True)
def _required_env_vars(monkeypatch):
    """Patch all mandatory config env vars so module imports never KeyError."""
    monkeypatch.setenv("TELEGRAM_TOKEN", "test-telegram-token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-supabase-key")
    monkeypatch.setenv("REDDIT_CLIENT_ID", "test-reddit-client-id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test-reddit-secret")
    monkeypatch.setenv("REDDIT_USER_AGENT", "AutoSO/test")
    monkeypatch.setenv("WHITELISTED_USER_IDS", "12345")
```

- [ ] **Step 2: Write failing test**

Create `tests/__init__.py`, `tests/test_config.py`:

```python
# tests/test_config.py
import importlib
import os
import pytest

def test_whitelisted_user_ids_parsed_as_integers(monkeypatch):
    monkeypatch.setenv("WHITELISTED_USER_IDS", "111,222, 333")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tok")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
    monkeypatch.setenv("SUPABASE_URL", "http://x")
    monkeypatch.setenv("SUPABASE_KEY", "k")
    monkeypatch.setenv("REDDIT_CLIENT_ID", "r")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "s")

    import autoso.config as cfg
    importlib.reload(cfg)
    assert cfg.WHITELISTED_USER_IDS == {111, 222, 333}

def test_empty_whitelist_gives_empty_set(monkeypatch):
    monkeypatch.setenv("WHITELISTED_USER_IDS", "")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tok")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
    monkeypatch.setenv("SUPABASE_URL", "http://x")
    monkeypatch.setenv("SUPABASE_KEY", "k")
    monkeypatch.setenv("REDDIT_CLIENT_ID", "r")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "s")

    import autoso.config as cfg
    importlib.reload(cfg)
    assert cfg.WHITELISTED_USER_IDS == set()
```

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest tests/test_config.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `autoso.config` does not exist yet.

- [ ] **Step 4: Create `autoso/config.py`**

```python
# autoso/config.py
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN: str = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY: str = os.environ["ANTHROPIC_API_KEY"]
SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_KEY: str = os.environ["SUPABASE_KEY"]
REDDIT_CLIENT_ID: str = os.environ["REDDIT_CLIENT_ID"]
REDDIT_CLIENT_SECRET: str = os.environ["REDDIT_CLIENT_SECRET"]
REDDIT_USER_AGENT: str = os.environ.get("REDDIT_USER_AGENT", "AutoSO/1.0")

WHITELISTED_USER_IDS: set[int] = {
    int(uid.strip())
    for uid in os.environ.get("WHITELISTED_USER_IDS", "").split(",")
    if uid.strip()
}

CHROMADB_PATH: str = os.environ.get("CHROMADB_PATH", "./data/chromadb")
USE_OLLAMA: bool = os.environ.get("USE_OLLAMA", "false").lower() == "true"
OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "llama3.2")
CLAUDE_MODEL: str = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/test_config.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add autoso/__init__.py autoso/config.py tests/__init__.py tests/test_config.py
git commit -m "feat: add config module with whitelist parsing"
```

---

## Task 3: Auth Middleware

**Files:**
- Create: `autoso/bot/__init__.py`
- Create: `autoso/bot/auth.py`
- Create: `tests/test_auth.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_auth.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture
def authorized_update():
    update = MagicMock()
    update.effective_user.id = 12345
    update.message.reply_text = AsyncMock()
    return update

@pytest.fixture
def unauthorized_update():
    update = MagicMock()
    update.effective_user.id = 99999
    update.message.reply_text = AsyncMock()
    return update

@pytest.fixture
def mock_context():
    return MagicMock()

async def test_authorized_user_passes_through(authorized_update, mock_context):
    with patch("autoso.config.WHITELISTED_USER_IDS", {12345}):
        from autoso.bot.auth import require_auth
        called = []

        @require_auth
        async def handler(update, context):
            called.append(True)

        await handler(authorized_update, mock_context)

    assert called == [True]
    authorized_update.message.reply_text.assert_not_called()

async def test_unauthorized_user_is_rejected(unauthorized_update, mock_context):
    with patch("autoso.config.WHITELISTED_USER_IDS", {12345}):
        from autoso.bot.auth import require_auth
        called = []

        @require_auth
        async def handler(update, context):
            called.append(True)

        await handler(unauthorized_update, mock_context)

    assert called == []
    unauthorized_update.message.reply_text.assert_called_once_with(
        "Unauthorised. Contact the bot administrator to request access."
    )

async def test_handler_return_value_preserved(authorized_update, mock_context):
    with patch("autoso.config.WHITELISTED_USER_IDS", {12345}):
        from autoso.bot.auth import require_auth

        @require_auth
        async def handler(update, context):
            return "result"

        result = await handler(authorized_update, mock_context)

    assert result == "result"


async def test_unauthorized_user_with_no_message_does_not_raise(mock_context):
    """Callback queries have no update.message — must not AttributeError."""
    update = MagicMock()
    update.effective_user.id = 99999
    update.message = None
    update.effective_chat.id = 111

    mock_context.bot = AsyncMock()
    mock_context.bot.send_message = AsyncMock()

    with patch("autoso.config.WHITELISTED_USER_IDS", {12345}):
        from autoso.bot.auth import require_auth
        called = []

        @require_auth
        async def handler(update, context):
            called.append(True)

        await handler(update, mock_context)

    assert called == []
    mock_context.bot.send_message.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_auth.py -v
```

Expected: `ImportError` — `autoso.bot.auth` does not exist.

- [ ] **Step 3: Create `autoso/bot/__init__.py`**

Empty file.

- [ ] **Step 4: Create `autoso/bot/auth.py`**

```python
# autoso/bot/auth.py
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
import autoso.config as config

_UNAUTH_MESSAGE = "Unauthorised. Contact the bot administrator to request access."


def require_auth(handler):
    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in config.WHITELISTED_USER_IDS:
            # update.message is None for callback queries and inline queries
            if update.message:
                await update.message.reply_text(_UNAUTH_MESSAGE)
            elif update.effective_chat:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=_UNAUTH_MESSAGE,
                )
            return
        return await handler(update, context)
    return wrapper
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/test_auth.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add autoso/bot/__init__.py autoso/bot/auth.py tests/test_auth.py
git commit -m "feat: add whitelist auth decorator"
```

---

## Task 4: Bot Scaffold

**Files:**
- Create: `autoso/bot/handlers.py`
- Create: `autoso/bot/main.py`

No tests for this task — handlers call `run_pipeline` which doesn't exist yet; full handler tests are in Phase 1b.

- [ ] **Step 1: Create `autoso/bot/handlers.py`**

```python
# autoso/bot/handlers.py
import asyncio
import functools
import logging
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from autoso.bot.auth import require_auth

logger = logging.getLogger(__name__)

TELEGRAM_MAX_LENGTH = 4096

# Shared executor — pipeline runs (scrape + LLM) are CPU/IO-heavy synchronous work.
# Running them in a thread pool keeps the event loop free for other Telegram updates.
_pipeline_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="pipeline")


def _is_valid_url(text: str) -> bool:
    try:
        parsed = urlparse(text)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


@require_auth
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "AutoSO ready.\n\n"
        "/texture <url> [title] — Texture analysis\n"
        "/bucket <url> [title] — Bucket analysis"
    )


@require_auth
async def texture_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _handle_analysis(update, context, mode="texture")


@require_auth
async def bucket_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _handle_analysis(update, context, mode="bucket")


async def _handle_analysis(
    update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str
):
    args = context.args
    if not args:
        await update.message.reply_text(f"Usage: /{mode} <url> [optional title]")
        return

    url = args[0]
    if not _is_valid_url(url):
        await update.message.reply_text(
            f"Invalid URL: {url!r}\nUsage: /{mode} <url> [optional title]"
        )
        return

    provided_title = " ".join(args[1:]) if len(args) > 1 else None

    await update.message.reply_text("Processing... this may take a minute.")

    try:
        # Imported here so Phase 1a works without Phase 1b installed.
        # run_pipeline is synchronous and calls Playwright + LLM — it must NOT
        # run directly in the async handler (blocks the event loop). Dispatch to
        # the thread-pool executor so the event loop stays responsive.
        from autoso.pipeline.pipeline import run_pipeline

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            _pipeline_executor,
            functools.partial(run_pipeline, url=url, mode=mode, provided_title=provided_title),
        )
        output = result.output

        if len(output) > TELEGRAM_MAX_LENGTH:
            logger.error(
                "Output exceeds Telegram limit: %d chars, run_id=%s",
                len(output),
                result.run_id,
            )
            await update.message.reply_text(
                f"Analysis complete but output is too long ({len(output)} characters). "
                f"View full output in the web UI (run ID: {result.run_id})."
            )
            return

        # Try Markdown formatting (titles use *bold*). Fall back to plain text if
        # the LLM output contains characters that break Telegram's Markdown parser.
        try:
            await update.message.reply_text(output, parse_mode="Markdown")
        except BadRequest:
            logger.warning("Markdown parse failed for run_id=%s — sending plain text", result.run_id)
            await update.message.reply_text(output)

    except Exception:
        logger.exception("Pipeline error for url=%s mode=%s", url, mode)
        await update.message.reply_text(
            "An error occurred while processing your request. Check logs for details."
        )
```

- [ ] **Step 2: Create `autoso/bot/main.py`**

```python
# autoso/bot/main.py
import logging
from telegram.ext import Application, CommandHandler
from autoso.config import TELEGRAM_TOKEN
from autoso.bot.handlers import start_handler, texture_handler, bucket_handler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("texture", texture_handler))
    app.add_handler(CommandHandler("bucket", bucket_handler))
    app.run_polling()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verify imports are clean**

```bash
python -c "from autoso.bot.main import main; print('OK')"
```

Expected: `OK` (may raise missing env var error — that's fine, means imports work).

- [ ] **Step 4: Commit**

```bash
git add autoso/bot/handlers.py autoso/bot/main.py
git commit -m "feat: add bot scaffold with /start, /texture, /bucket stubs"
```

---

## Task 5: Scraper Models

**Files:**
- Create: `autoso/scraping/__init__.py`
- Create: `autoso/scraping/models.py`
- Create: `tests/test_scraping/__init__.py`
- Create: `tests/test_scraping/test_models.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_scraping/test_models.py
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_scraping/test_models.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Create `autoso/scraping/__init__.py`** and `tests/test_scraping/__init__.py`**

```bash
touch autoso/scraping/__init__.py tests/test_scraping/__init__.py
```

- [ ] **Step 4: Create `autoso/scraping/models.py`**

```python
# autoso/scraping/models.py
from dataclasses import dataclass, field
from typing import List


@dataclass
class Comment:
    platform: str      # "reddit" | "instagram" | "facebook"
    text: str
    comment_id: str    # platform-specific ID or synthetic (e.g. "ig_42")
    position: int      # 0-indexed order in the comment list


@dataclass
class Post:
    title: str
    content: str       # post body text
    url: str
    platform: str
    comments: List[Comment] = field(default_factory=list)
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/test_scraping/test_models.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add autoso/scraping/__init__.py autoso/scraping/models.py \
        tests/test_scraping/__init__.py tests/test_scraping/test_models.py
git commit -m "feat: add Comment and Post scraper models"
```

---

## Task 6: Scraper Factory + Platform Detection

**Files:**
- Create: `autoso/scraping/base.py`
- Create: `tests/test_scraping/test_base.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_scraping/test_base.py
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_scraping/test_base.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Create `autoso/scraping/base.py`**

```python
# autoso/scraping/base.py
from urllib.parse import urlparse


def detect_platform(url: str) -> str:
    """Detect the social platform from a URL.

    Uses hostname matching (not substring-in-full-URL) to avoid false positives
    such as "notfb.com" matching the naive '"fb.com" in url' check.
    """
    hostname = urlparse(url).hostname or ""
    # Strip leading "www." / "m." for uniform matching
    bare = hostname.removeprefix("www.").removeprefix("m.")

    if bare == "reddit.com" or bare.endswith(".reddit.com"):
        return "reddit"
    if bare == "instagram.com" or bare.endswith(".instagram.com"):
        return "instagram"
    if bare == "facebook.com" or bare.endswith(".facebook.com") or bare == "fb.com":
        return "facebook"
    raise ValueError(f"Unsupported platform for URL: {url}")


def get_scraper(url: str):
    """Return the appropriate scraper instance for the given URL."""
    platform = detect_platform(url)
    if platform == "reddit":
        from autoso.scraping.reddit import RedditScraper
        return RedditScraper()
    if platform == "instagram":
        from autoso.scraping.instagram import InstagramScraper
        return InstagramScraper()
    if platform == "facebook":
        from autoso.scraping.facebook import FacebookScraper
        return FacebookScraper()
    # detect_platform raises ValueError for unknowns, so this is unreachable
    raise ValueError(f"No scraper registered for platform: {platform}")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_scraping/test_base.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add autoso/scraping/base.py tests/test_scraping/test_base.py
git commit -m "feat: add scraper factory and platform detection"
```

---

## Task 7: Reddit Scraper

**Files:**
- Create: `autoso/scraping/reddit.py`
- Create: `tests/test_scraping/test_reddit.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_scraping/test_reddit.py
import pytest
from unittest.mock import MagicMock, patch
from autoso.scraping.reddit import RedditScraper
from autoso.scraping.models import Post, Comment


def _make_mock_comment(body: str, id: str, pos: int) -> MagicMock:
    c = MagicMock()
    c.body = body
    c.id = id
    return c


def _make_mock_submission(title: str, selftext: str, comments: list) -> MagicMock:
    sub = MagicMock()
    sub.title = title
    sub.selftext = selftext
    sub.comments.list.return_value = comments
    sub.comments.replace_more = MagicMock()
    return sub


@patch("autoso.scraping.reddit.praw.Reddit")
def test_scrape_returns_post(mock_reddit_cls):
    raw_comments = [
        _make_mock_comment("NS is important for defence", "c1", 0),
        _make_mock_comment("I support MINDEF policies", "c2", 1),
    ]
    sub = _make_mock_submission("Test Post", "Post body here", raw_comments)
    mock_reddit_cls.return_value.submission.return_value = sub

    scraper = RedditScraper()
    post = scraper.scrape("https://www.reddit.com/r/singapore/comments/abc")

    assert isinstance(post, Post)
    assert post.platform == "reddit"
    assert post.title == "Test Post"
    assert post.content == "Post body here"
    assert len(post.comments) == 2
    assert post.comments[0].text == "NS is important for defence"
    assert post.comments[0].comment_id == "c1"
    assert post.comments[0].position == 0
    assert post.comments[1].position == 1


@patch("autoso.scraping.reddit.praw.Reddit")
def test_scrape_filters_deleted_comments(mock_reddit_cls):
    raw_comments = [
        _make_mock_comment("[deleted]", "d1", 0),
        _make_mock_comment("[removed]", "d2", 1),
        _make_mock_comment("Normal comment", "c1", 2),
    ]
    sub = _make_mock_submission("Post", "", raw_comments)
    mock_reddit_cls.return_value.submission.return_value = sub

    scraper = RedditScraper()
    post = scraper.scrape("https://www.reddit.com/r/test/comments/xyz")

    assert len(post.comments) == 1
    assert post.comments[0].text == "Normal comment"


@patch("autoso.scraping.reddit.praw.Reddit")
def test_scrape_uses_title_as_content_when_no_selftext(mock_reddit_cls):
    raw_comments = [_make_mock_comment("Good point", "c1", 0)]
    sub = _make_mock_submission("Link Post Title", "", raw_comments)
    mock_reddit_cls.return_value.submission.return_value = sub

    scraper = RedditScraper()
    post = scraper.scrape("https://www.reddit.com/r/test/comments/xyz")

    assert post.content == "Link Post Title"


@patch("autoso.scraping.reddit.praw.Reddit")
def test_scrape_keeps_comment_starting_with_deleted_word_in_context(mock_reddit_cls):
    """A real comment that starts with the word 'deleted' in context must NOT be filtered."""
    raw_comments = [
        _make_mock_comment("[deleted] is a common meme response", "c1", 0),  # should be filtered
        _make_mock_comment("The deleted scene was actually good", "c2", 1),  # must be kept
    ]
    sub = _make_mock_submission("Post", "body", raw_comments)
    mock_reddit_cls.return_value.submission.return_value = sub

    scraper = RedditScraper()
    post = scraper.scrape("https://www.reddit.com/r/test/comments/xyz")

    texts = [c.text for c in post.comments]
    assert "[deleted] is a common meme response" not in texts  # exact match filtered
    assert "The deleted scene was actually good" in texts       # partial match kept


@patch("autoso.scraping.reddit.praw.Reddit")
def test_scrape_positions_are_sequential_after_filtering(mock_reddit_cls):
    """Positions must be 0-indexed and contiguous after deleted comments are dropped."""
    raw_comments = [
        _make_mock_comment("[deleted]", "d1", 0),
        _make_mock_comment("First real comment", "c1", 1),
        _make_mock_comment("Second real comment", "c2", 2),
    ]
    sub = _make_mock_submission("Post", "body", raw_comments)
    mock_reddit_cls.return_value.submission.return_value = sub

    scraper = RedditScraper()
    post = scraper.scrape("https://www.reddit.com/r/test/comments/xyz")

    assert len(post.comments) == 2
    assert post.comments[0].position == 1  # position reflects original list index
    assert post.comments[1].position == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_scraping/test_reddit.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Create `autoso/scraping/reddit.py`**

```python
# autoso/scraping/reddit.py
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
            if c.body in ("[deleted]", "[removed]"):
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_scraping/test_reddit.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add autoso/scraping/reddit.py tests/test_scraping/test_reddit.py
git commit -m "feat: add Reddit scraper using PRAW"
```

---

## Task 8: Playwright Base (Session Management)

**Files:**
- Create: `autoso/scraping/playwright_base.py`

No isolated tests here — behaviour is tested via the IG/FB scraper tests.

- [ ] **Step 1: Create `autoso/scraping/playwright_base.py`**

```python
# autoso/scraping/playwright_base.py
import asyncio
import json
import random
from pathlib import Path
from playwright.async_api import async_playwright, Browser, BrowserContext

# Absolute path anchored to the project root (two levels above this file's package).
# Using a relative "./data/sessions" would break if the process is started from any
# directory other than the project root.
SESSION_DIR = Path(__file__).parent.parent.parent / "data" / "sessions"


class PlaywrightScraper:
    def __init__(self, platform: str):
        self.platform = platform
        self._session_file = SESSION_DIR / f"{platform}_session.json"
        SESSION_DIR.mkdir(parents=True, exist_ok=True)

    async def _get_context(self, browser: Browser) -> BrowserContext:
        storage_state = None
        if self._session_file.exists():
            with open(self._session_file) as f:
                storage_state = json.load(f)

        return await browser.new_context(
            storage_state=storage_state,
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            timezone_id="Asia/Singapore",
        )

    async def _save_session(self, context: BrowserContext) -> None:
        state = await context.storage_state()
        with open(self._session_file, "w") as f:
            json.dump(state, f)

    async def _human_delay(self, min_ms: int = 500, max_ms: int = 2000) -> None:
        await asyncio.sleep(random.uniform(min_ms, max_ms) / 1000)
```

- [ ] **Step 2: Verify import**

```bash
python -c "from autoso.scraping.playwright_base import PlaywrightScraper; print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Write session persistence tests**

```python
# tests/test_scraping/test_playwright_base.py
import json
import pytest
from unittest.mock import AsyncMock
from autoso.scraping.playwright_base import PlaywrightScraper


@pytest.mark.asyncio
async def test_get_context_loads_saved_session(tmp_path):
    """If a session file exists it is passed as storage_state to new_context."""
    scraper = PlaywrightScraper("instagram")
    session_file = tmp_path / "instagram_session.json"
    session_data = {
        "cookies": [{"name": "sessionid", "value": "abc123", "domain": ".instagram.com"}]
    }
    session_file.write_text(json.dumps(session_data))
    scraper._session_file = session_file

    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=AsyncMock())
    await scraper._get_context(mock_browser)

    call_kwargs = mock_browser.new_context.call_args.kwargs
    assert call_kwargs["storage_state"]["cookies"][0]["name"] == "sessionid"


@pytest.mark.asyncio
async def test_get_context_no_storage_state_when_no_session_file(tmp_path):
    """If no session file exists, storage_state is None."""
    scraper = PlaywrightScraper("facebook")
    scraper._session_file = tmp_path / "facebook_session.json"  # doesn't exist

    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=AsyncMock())
    await scraper._get_context(mock_browser)

    call_kwargs = mock_browser.new_context.call_args.kwargs
    assert call_kwargs.get("storage_state") is None


@pytest.mark.asyncio
async def test_save_session_writes_to_file(tmp_path):
    """_save_session writes the context's storage_state to disk."""
    scraper = PlaywrightScraper("instagram")
    scraper._session_file = tmp_path / "instagram_session.json"

    mock_context = AsyncMock()
    mock_context.storage_state = AsyncMock(return_value={"cookies": [], "origins": []})
    await scraper._save_session(mock_context)

    assert scraper._session_file.exists()
    data = json.loads(scraper._session_file.read_text())
    assert "cookies" in data
```

- [ ] **Step 4: Run session tests**

```bash
pytest tests/test_scraping/test_playwright_base.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add autoso/scraping/playwright_base.py tests/test_scraping/test_playwright_base.py
git commit -m "feat: add Playwright base scraper with cookie session management"
```

---

## Task 9: Instagram Scraper

**Files:**
- Create: `autoso/scraping/instagram.py`
- Create: `tests/test_scraping/test_instagram.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_scraping/test_instagram.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from autoso.scraping.instagram import InstagramScraper
from autoso.scraping.models import Post


def _make_text_el(text: str) -> AsyncMock:
    el = AsyncMock()
    el.inner_text = AsyncMock(return_value=text)
    return el


def _make_locator_for(texts: list[str]) -> AsyncMock:
    """Return a mock locator whose .nth(i).inner_text() yields texts[i]."""
    loc = AsyncMock()
    loc.count = AsyncMock(return_value=len(texts))
    loc.nth.side_effect = lambda i: _make_text_el(texts[i])
    return loc


def _build_page_mock(
    post_content: str,
    og_title: str,
    comment_texts: list[str],
    load_more_visible: bool = False,
) -> AsyncMock:
    """
    Build a fully-wired page mock without mixing side_effect and return_value
    on the same locator mock (which would cause the return_value to be silently
    ignored).  Instead we use a single side_effect dispatch table keyed by the
    selector string.
    """
    page = AsyncMock()

    # post content: article ... span selector → .first.inner_text()
    post_el = AsyncMock()
    post_el.inner_text = AsyncMock(return_value=post_content)
    post_loc = AsyncMock()
    post_loc.first = post_el

    # og:title: meta[property='og:title'] → .get_attribute("content")
    title_el = AsyncMock()
    title_el.get_attribute = AsyncMock(return_value=og_title)
    title_loc = AsyncMock()
    # locator returns the element directly (no .first needed for meta)
    title_loc.__aiter__ = AsyncMock(return_value=iter([title_el]))
    # _extract_post_title calls page.locator(selector) and then get_attribute
    # on the returned locator object itself
    title_loc.get_attribute = AsyncMock(return_value=og_title)

    # comments: article ul li span[dir='auto'] → .count() / .nth(i)
    comment_loc = _make_locator_for(comment_texts)

    selector_map = {
        "article h1, article div[data-testid='post-content'], article span": post_loc,
        "meta[property='og:title']": title_loc,
        "article ul li span[dir='auto']": comment_loc,
    }

    def locator_side_effect(selector):
        return selector_map.get(selector, AsyncMock())

    page.locator.side_effect = locator_side_effect

    # _expand_comments: get_by_text("Load more comments").first.is_visible()
    load_more = AsyncMock()
    load_more.is_visible = AsyncMock(return_value=load_more_visible)
    page.get_by_text.return_value.first = load_more

    return page


@pytest.mark.asyncio
@patch("autoso.scraping.instagram.async_playwright")
@patch("autoso.scraping.instagram.stealth_async", new_callable=AsyncMock)
async def test_scrape_returns_post_with_correct_platform(mock_stealth, mock_pw):
    """_scrape_async returns a Post with platform='instagram' and correct URL."""
    scraper = InstagramScraper()
    comment_texts = [
        "Great photo from the SAF exercise!",
        "Really proud of our NSmen",
        "Amazing bilateral relations event",
    ]
    mock_page = _build_page_mock(
        post_content="SAF event post body",
        og_title="SAF Event",
        comment_texts=comment_texts,
    )

    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_context.storage_state = AsyncMock(return_value={})
    mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_pw.return_value)
    mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_pw.return_value.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.new_page = AsyncMock(return_value=mock_page)

    url = "https://www.instagram.com/p/ABC123/"
    post = await scraper._scrape_async(url)

    assert isinstance(post, Post)
    assert post.platform == "instagram"
    assert post.url == url


@pytest.mark.asyncio
@patch("autoso.scraping.instagram.async_playwright")
@patch("autoso.scraping.instagram.stealth_async", new_callable=AsyncMock)
async def test_scrape_extracts_comments(mock_stealth, mock_pw):
    """Comments longer than 10 chars are extracted into the Post."""
    scraper = InstagramScraper()
    comment_texts = [
        "NS training builds character and discipline",
        "SAF personnel were very professional",
        "ok",  # too short, must be filtered out
    ]
    mock_page = _build_page_mock(
        post_content="Post body",
        og_title="Title",
        comment_texts=comment_texts,
    )

    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_context.storage_state = AsyncMock(return_value={})
    mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_pw.return_value)
    mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_pw.return_value.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.new_page = AsyncMock(return_value=mock_page)

    post = await scraper._scrape_async("https://www.instagram.com/p/XYZ/")

    # "ok" is 2 chars — below the 10-char threshold — must be dropped
    extracted_texts = [c.text for c in post.comments]
    assert "NS training builds character and discipline" in extracted_texts
    assert "SAF personnel were very professional" in extracted_texts
    assert "ok" not in extracted_texts
    assert len(post.comments) == 2
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_scraping/test_instagram.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Create `autoso/scraping/instagram.py`**

```python
# autoso/scraping/instagram.py
import asyncio
from typing import List
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from autoso.scraping.playwright_base import PlaywrightScraper
from autoso.scraping.models import Comment, Post


class InstagramScraper(PlaywrightScraper):
    def __init__(self):
        super().__init__("instagram")

    def scrape(self, url: str) -> Post:
        return asyncio.run(self._scrape_async(url))

    async def _scrape_async(self, url: str) -> Post:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await self._get_context(browser)
            page = await context.new_page()
            await stealth_async(page)

            await page.goto(url, wait_until="networkidle", timeout=30_000)
            await self._human_delay(1000, 3000)

            post_content = await self._extract_post_content(page)
            post_title = await self._extract_post_title(page, url)
            await self._expand_comments(page)
            comments = await self._extract_comments(page)

            await self._save_session(context)
            await browser.close()

            return Post(
                title=post_title,
                content=post_content,
                url=url,
                platform="instagram",
                comments=comments,
            )

    async def _extract_post_content(self, page) -> str:
        try:
            el = page.locator(
                "article h1, article div[data-testid='post-content'], article span"
            ).first
            return await el.inner_text(timeout=5000)
        except Exception:
            return ""

    async def _extract_post_title(self, page, url: str) -> str:
        try:
            el = page.locator("meta[property='og:title']")
            return await el.get_attribute("content") or url
        except Exception:
            return url

    async def _expand_comments(self, page) -> None:
        for _ in range(20):
            try:
                btn = page.get_by_text("Load more comments").first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await self._human_delay(800, 1500)
                else:
                    break
            except Exception:
                break

    async def _extract_comments(self, page) -> List[Comment]:
        els = page.locator("article ul li span[dir='auto']")
        count = await els.count()
        comments = []
        for i in range(count):
            try:
                text = (await els.nth(i).inner_text()).strip()
                if len(text) > 10 and not text.lower().startswith("view"):
                    comments.append(
                        Comment(
                            platform="instagram",
                            text=text,
                            comment_id=f"ig_{i}",
                            position=i,
                        )
                    )
            except Exception:
                continue
        return comments
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_scraping/test_instagram.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add autoso/scraping/instagram.py tests/test_scraping/test_instagram.py
git commit -m "feat: add Instagram scraper with Playwright + stealth"
```

---

## Task 10: Facebook Scraper

**Files:**
- Create: `autoso/scraping/facebook.py`
- Create: `tests/test_scraping/test_facebook.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_scraping/test_facebook.py
import pytest
from unittest.mock import AsyncMock, patch
from autoso.scraping.facebook import FacebookScraper
from autoso.scraping.models import Post


@pytest.mark.asyncio
@patch("autoso.scraping.facebook.async_playwright")
@patch("autoso.scraping.facebook.stealth_async", new_callable=AsyncMock)
async def test_scrape_returns_post(mock_stealth, mock_pw):
    scraper = FacebookScraper()

    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_pw.return_value)
    mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_pw.return_value.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.storage_state = AsyncMock(return_value={})

    post_el = AsyncMock()
    post_el.inner_text = AsyncMock(return_value="FB post body")
    mock_page.locator.return_value.first = post_el

    title_el = AsyncMock()
    title_el.get_attribute = AsyncMock(return_value="FB Post")
    mock_page.locator.return_value = title_el

    load_more = AsyncMock()
    load_more.is_visible = AsyncMock(return_value=False)
    mock_page.get_by_text.return_value.first = load_more

    comment_loc = AsyncMock()
    comment_texts = ["SAF exercise was great", "Good bilateral relations"]
    comment_loc.count = AsyncMock(return_value=len(comment_texts))

    def make_text_el(text):
        el = AsyncMock()
        el.inner_text = AsyncMock(return_value=text)
        return el

    comment_loc.nth.side_effect = lambda i: make_text_el(comment_texts[i])
    mock_page.locator.return_value = comment_loc

    post = await scraper._scrape_async("https://www.facebook.com/mindef/posts/123")

    assert isinstance(post, Post)
    assert post.platform == "facebook"
    assert post.url == "https://www.facebook.com/mindef/posts/123"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_scraping/test_facebook.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Create `autoso/scraping/facebook.py`**

```python
# autoso/scraping/facebook.py
import asyncio
import re
from typing import List
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from autoso.scraping.playwright_base import PlaywrightScraper
from autoso.scraping.models import Comment, Post


class FacebookScraper(PlaywrightScraper):
    def __init__(self):
        super().__init__("facebook")

    def scrape(self, url: str) -> Post:
        return asyncio.run(self._scrape_async(url))

    async def _scrape_async(self, url: str) -> Post:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await self._get_context(browser)
            page = await context.new_page()
            await stealth_async(page)

            await page.goto(url, wait_until="networkidle", timeout=30_000)
            await self._human_delay(1000, 3000)

            post_content = await self._extract_post_content(page)
            post_title = await self._extract_post_title(page, url)
            await self._expand_comments(page)
            comments = await self._extract_comments(page)

            await self._save_session(context)
            await browser.close()

            return Post(
                title=post_title,
                content=post_content,
                url=url,
                platform="facebook",
                comments=comments,
            )

    async def _extract_post_content(self, page) -> str:
        try:
            el = page.locator(
                "[data-ad-comet-preview='message'], [data-testid='post_message']"
            ).first
            return await el.inner_text(timeout=5000)
        except Exception:
            return ""

    async def _extract_post_title(self, page, url: str) -> str:
        try:
            el = page.locator("meta[property='og:title']")
            return await el.get_attribute("content") or url
        except Exception:
            return url

    async def _expand_comments(self, page) -> None:
        pattern = re.compile(r"View \d+ more comment|View more comment", re.I)
        for _ in range(20):
            try:
                btn = page.get_by_text(pattern).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await self._human_delay(1000, 2000)
                else:
                    break
            except Exception:
                break

    async def _extract_comments(self, page) -> List[Comment]:
        els = page.locator("[aria-label='Comment'] span[dir='auto']")
        count = await els.count()
        comments = []
        for i in range(count):
            try:
                text = (await els.nth(i).inner_text()).strip()
                if len(text) > 10:
                    comments.append(
                        Comment(
                            platform="facebook",
                            text=text,
                            comment_id=f"fb_{i}",
                            position=i,
                        )
                    )
            except Exception:
                continue
        return comments
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_scraping/test_facebook.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Run full test suite**

```bash
pytest -v
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add autoso/scraping/facebook.py tests/test_scraping/test_facebook.py
git commit -m "feat: add Facebook scraper with Playwright + stealth"
```

---

## Task 11: Smoke Test — Full Scraping Layer

This task has no new files. It validates that all scrapers are reachable via the factory.

- [ ] **Step 1: Write integration smoke test**

```python
# tests/test_scraping/test_factory.py
from unittest.mock import patch, MagicMock
from autoso.scraping.base import get_scraper
from autoso.scraping.reddit import RedditScraper
from autoso.scraping.instagram import InstagramScraper
from autoso.scraping.facebook import FacebookScraper


@patch("autoso.scraping.reddit.praw.Reddit")
def test_factory_returns_reddit_scraper(mock_reddit):
    # RedditScraper.__init__ calls praw.Reddit() — mock it so no live connection
    s = get_scraper("https://www.reddit.com/r/singapore/comments/abc")
    assert isinstance(s, RedditScraper)


def test_factory_returns_instagram_scraper():
    # InstagramScraper has no __init__ side effects (Playwright is lazy)
    s = get_scraper("https://www.instagram.com/p/ABC123/")
    assert isinstance(s, InstagramScraper)


def test_factory_returns_facebook_scraper():
    s = get_scraper("https://www.facebook.com/mindef/posts/123")
    assert isinstance(s, FacebookScraper)


def test_factory_raises_for_unsupported_url():
    import pytest
    with pytest.raises(ValueError, match="Unsupported platform"):
        get_scraper("https://twitter.com/mindef/status/1")
```

- [ ] **Step 2: Run factory tests**

```bash
pytest tests/test_scraping/test_factory.py -v
```

Expected: 4 passed.

- [ ] **Step 3: Run full suite**

```bash
pytest -v
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_scraping/test_factory.py
git commit -m "test: add scraper factory smoke tests — Phase 1a complete"
```

---

## Manual Integration Test (Not Automated)

Once a `.env` file is populated and IG/FB login cookies are saved, run this manually to validate live scraping:

```bash
# Reddit (no auth needed)
python -c "
from autoso.scraping.reddit import RedditScraper
post = RedditScraper().scrape('https://www.reddit.com/r/singapore/comments/REAL_ID')
print(f'{post.title} — {len(post.comments)} comments')
"

# Instagram (requires cookies in data/sessions/instagram_session.json)
python -c "
from autoso.scraping.instagram import InstagramScraper
post = InstagramScraper().scrape('https://www.instagram.com/p/REAL_ID/')
print(f'{post.title} — {len(post.comments)} comments')
"
```

If 0 comments returned from IG/FB: check session file, rotate proxy, or escalate to Approach 2 (Brave) per `plan.md` Section 7.
