# AutoSO

Telegram bot for MINDEF/SAF Sense Officers. Scrapes social media posts and runs RAG-powered sentiment analysis with source citations. Also transcribes audio/video to Word documents.

## Commands

| Command | Description |
|---------|-------------|
| `/texture <url> [title]` | Free-form sentiment breakdown with % themes |
| `/bucket <url> [title]` | Classifies comments into MINDEF/SAF sentiment buckets |
| `/transcribe <url> [title]` | Downloads audio, transcribes with Whisper, returns .docx |

Supported platforms: Reddit, Instagram, Facebook, TikTok, YouTube, HardwareZone.

---

## Prerequisites

- Python 3.11+
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- Anthropic API key
- Supabase project

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

Edit `.env`:

```env
TELEGRAM_TOKEN=your_telegram_bot_token_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key_here
WHITELISTED_USER_IDS=123456789,987654321
CHROMADB_PATH=./data/chromadb
USE_OLLAMA=false
CLAUDE_MODEL=claude-sonnet-4-6
PROXY_URL=
CITATION_UI_BASE_URL=http://localhost:8000
YOUTUBE_COOKIES_FILE=
```

To find your Telegram user ID, message [@userinfobot](https://t.me/userinfobot).

### 4. Set up Supabase

Run the migrations in order in the Supabase SQL Editor:

1. `migrations/001_initial_schema.sql`
2. `migrations/002_transcripts_table.sql`

### 5. Platform setup

Not all platforms work out of the box. See the table and instructions below.

| Platform | Works by default? | What's needed |
|---|---|---|
| **Facebook** | ✅ Public posts | Nothing |
| **HardwareZone** | ✅ Public forum | Nothing |
| **Reddit** | ⚠️ Residential IP only | `PROXY_URL` on cloud/datacenter servers |
| **YouTube** | ⚠️ Residential IP only | `YOUTUBE_COOKIES_FILE` on cloud/datacenter servers |
| **TikTok** | ⚠️ Session + residential IP | Session file + `PROXY_URL` on cloud servers |
| **Instagram** | ⚠️ Session required | Session file; `PROXY_URL` recommended |

#### Reddit

Reddit blocks requests from datacenter and cloud IPs (e.g. Codespaces, EC2, GCP). On a residential machine it works without any extra config. On a cloud server, set a residential or ISP proxy:

```env
PROXY_URL=socks5://user:pass@host:port
```

#### YouTube

On residential IPs yt-dlp works without any extra config. On cloud/datacenter IPs, YouTube detects the request as a bot. Fix: export your YouTube cookies from Chrome and point yt-dlp at the file.

1. Install the **[Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)** Chrome extension.
2. Go to [youtube.com](https://www.youtube.com) while signed in.
3. Click the extension → **Export** → save as e.g. `data/youtube_cookies.txt`.
4. Set in `.env`:
   ```env
   YOUTUBE_COOKIES_FILE=./data/youtube_cookies.txt
   ```

#### TikTok and Instagram

These platforms require a logged-in browser session. Run the login helper **on a local machine with a display** (not a headless server):

```bash
python scripts/save_session.py tiktok
python scripts/save_session.py instagram
```

A browser window opens — log in, then press Enter. The session is saved to `data/sessions/<platform>_session.json`. If running on a cloud server, transfer the file there after saving it locally.

TikTok also blocks requests from datacenter IPs even with a valid session; set `PROXY_URL` on cloud servers.

### 6. (Optional) Ingest the Bucket Holy Grail

The `/bucket` command uses reference documents to classify comments. Place your documents in `data/holy_grail/` and run:

```bash
python scripts/ingest_holy_grail.py data/holy_grail/
```

This accepts a file or directory (recursive). Re-running clears and rebuilds the index.

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

Set in `.env`:

```env
USE_OLLAMA=true
OLLAMA_MODEL=llama3.2
```

---

## Testing

Unit tests (fast, no external calls):

```bash
pytest
```

### Integration tests

Fill in URLs in [tests/integration/data.py](tests/integration/data.py), then run all platforms at once:

```bash
python tests/integration/run_all.py
```

Or run a single platform:

```bash
python -m autoso.diagnostics.scrape --url <post-url>   # auto-detects platform
python -m autoso.diagnostics.analyze --mode texture    # or --mode bucket
python -m autoso.diagnostics.telegram                  # Telegram getMe() liveness check
```

Each prints a JSON result and exits non-zero on failure.

The pytest integration suite (opt-in):

```bash
pytest tests/integration/ --run-integration -v
```

---

## Project structure

```
autoso/
├── bot/              # Telegram handlers, auth, entry point
├── diagnostics/      # Live-integration verifiers (scrape, analyze, telegram)
├── pipeline/         # RAG pipeline: indexing, citations, prompts, LLM config
├── scraping/         # Platform scrapers (Playwright + yt-dlp)
├── storage/          # Supabase integration
├── transcription/    # yt-dlp download, Whisper transcription, DOCX output
└── ui/               # FastAPI citation viewer

migrations/           # SQL schema files (run in Supabase)
scripts/              # Utility scripts (holy grail ingestion, session login helper)
data/
├── chromadb/         # Vector index (ChromaDB)
├── sessions/         # Playwright session cookies per platform
└── holy_grail/       # Bucket reference documents
tests/
├── integration/      # Live tests — fill data.py URLs, run run_all.py
└── ...               # Unit tests (mirror autoso/ structure)
```
