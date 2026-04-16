# autoso/pipeline/llm.py
from llama_index.core import Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
import autoso.config as config

import threading

_configure_lock = threading.Lock()
_configured = False


def configure_llm():
    """Configure both the LLM and the embedding model. Thread-safe, runs once."""
    global _configured
    if _configured:
        return Settings.llm

    with _configure_lock:
        if _configured:
            return Settings.llm

        if config.USE_OLLAMA:
            from llama_index.llms.ollama import Ollama
            llm = Ollama(model=config.OLLAMA_MODEL, request_timeout=300.0)
        else:
            from llama_index.llms.anthropic import Anthropic
            llm = Anthropic(model=config.CLAUDE_MODEL, api_key=config.ANTHROPIC_API_KEY)

        Settings.llm = llm
        Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5")
        _configured = True
        return llm
