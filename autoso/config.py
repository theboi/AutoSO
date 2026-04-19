# autoso/config.py
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN: str = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY: str = os.environ["ANTHROPIC_API_KEY"]
SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_KEY: str = os.environ["SUPABASE_KEY"]

WHITELISTED_USER_IDS: set[int] = {
    int(uid.strip())
    for uid in os.environ.get("WHITELISTED_USER_IDS", "").split(",")
    if uid.strip()
}

CHROMADB_PATH: str = os.environ.get("CHROMADB_PATH", "./data/chromadb")
USE_OLLAMA: bool = os.environ.get("USE_OLLAMA", "false").lower() == "true"
OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "llama3.2")
CLAUDE_MODEL: str = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

PROXY_URL: str | None = os.environ.get("PROXY_URL") or None
CITATION_UI_BASE_URL: str = os.environ.get("CITATION_UI_BASE_URL", "http://localhost:8000")
