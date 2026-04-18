# AutoSO

Telegram bot for MINDEF/SAF Sense Officers. Scrapes social media posts and runs RAG-powered sentiment analysis with source citations. Also transcribes audio/video to Word documents.

## Commands

| Command | Description |
|---------|-------------|
| `/texture <url> [title]` | Free-form sentiment breakdown with % themes |
| `/bucket <url> [title]` | Classifies comments into MINDEF/SAF sentiment buckets |
| `/transcribe <url> [title]` | Downloads audio, transcribes with Whisper, returns .docx |

Supported platforms: Reddit, Instagram, Facebook (texture/bucket), and any URL supported by yt-dlp (transcribe).

---

## Prerequisites

- Python 3.11+
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- Anthropic API key
- Supabase project
- Reddit API credentials (for Reddit scraping)
- A residential/ISP proxy (for Instagram and Facebook scraping)

---

## Setup

### 1. Clone and install

```bash
git clone <repo-url>
cd AutoSO
pip install -e ".[dev]"
```

### 2. Install Playwright browsers

```bash
playwright install chromium
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# Telegram
TELEGRAM_TOKEN=your_telegram_bot_token_here

# Anthropic
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key_here

# Reddit (PRAW) — required for Reddit scraping
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
REDDIT_USER_AGENT=AutoSO/1.0 by u/your_username

# Whitelist: comma-separated Telegram user IDs allowed to use the bot
WHITELISTED_USER_IDS=123456789,987654321

# ChromaDB — where vector indexes are stored
CHROMADB_PATH=./data/chromadb

# LLM mode — set USE_OLLAMA=true for local dev (no API credits)
USE_OLLAMA=false
OLLAMA_MODEL=llama3.2
CLAUDE_MODEL=claude-sonnet-4-6

# Proxy — residential/ISP proxy required for Instagram and Facebook scraping
PROXY_URL=

# Citation UI base URL — shown in Telegram when output exceeds 4096 chars
CITATION_UI_BASE_URL=http://localhost:8000
```

To find your Telegram user ID, message [@userinfobot](https://t.me/userinfobot).

### 4. Set up Supabase

Run the migrations in order in the Supabase SQL Editor:

1. `migrations/001_initial_schema.sql` — creates `analyses` and `citations` tables
2. `migrations/002_transcripts_table.sql` — creates `transcripts` table

### 5. (Optional) Ingest the Bucket Holy Grail

The `/bucket` command uses reference documents to classify comments. Place your documents in `data/holy_grail/` and run:

```bash
python scripts/ingest_holy_grail.py data/holy_grail/
```

This accepts a file or directory (recursive). Re-running clears and rebuilds the index. It persists in ChromaDB at `CHROMADB_PATH`.

---

## Running

### Bot

```bash
python -m autoso.bot.main
```

### Citation UI (FastAPI)

The web UI is used when analysis output exceeds Telegram's 4096-character limit.

```bash
uvicorn autoso.ui.app:app --host 0.0.0.0 --port 8000
```

Set `CITATION_UI_BASE_URL` in `.env` to the public URL where this is hosted.

---

## Local development with Ollama

To avoid API costs during development:

```bash
ollama pull llama3.2
```

Then set in `.env`:

```env
USE_OLLAMA=true
OLLAMA_MODEL=llama3.2
```

---

## Running tests

Unit tests (fast, no external calls):

```bash
pytest
```

### Integration tests

Integration tests hit real external services (Reddit, Instagram, Facebook, Anthropic, Telegram). They are skipped by default; opt in with `--run-integration`.

```bash
pytest tests/integration/ --run-integration -v
```

Each test also auto-skips if its required credentials are not real (i.e. still set to the test placeholders). To actually run them:

1. Fill in real values in `.env` for whichever services you want to test (`TELEGRAM_TOKEN`, `ANTHROPIC_API_KEY`, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`).
2. Fill in real URLs in [tests/integration/data.py](tests/integration/data.py) for `REDDIT_URL`, `INSTAGRAM_URL`, `FACEBOOK_URL`.
3. For Instagram/Facebook, save Playwright session cookies to `data/sessions/{instagram,facebook}_session.json` (log in interactively once).

### Standalone diagnostic CLIs

The same checks are exposed as runnable modules — useful for quickly verifying a single integration without pytest:

```bash
python -m autoso.diagnostics.scrape --url <post-url>      # auto-detects platform
python -m autoso.diagnostics.analyze --mode texture       # or --mode bucket
python -m autoso.diagnostics.telegram                     # Telegram getMe() liveness check
```

Each prints a JSON result and exits non-zero on failure.

---

## Project structure

```
autoso/
├── bot/              # Telegram handlers, auth, entry point
├── diagnostics/      # Live-integration verifiers (scrape, analyze, telegram)
├── pipeline/         # RAG pipeline: indexing, citations, prompts, LLM config
├── scraping/         # Reddit (PRAW), Instagram & Facebook (Playwright)
├── storage/          # Supabase integration
├── transcription/    # yt-dlp download, Whisper transcription, DOCX output
└── ui/               # FastAPI citation viewer

migrations/           # SQL schema files (run in Supabase)
scripts/              # Utility scripts (holy grail ingestion)
data/                 # Runtime data: ChromaDB, session files
tests/
├── integration/      # Opt-in tests against real services (--run-integration)
└── ...               # Unit tests (mirror autoso/ structure)
```
