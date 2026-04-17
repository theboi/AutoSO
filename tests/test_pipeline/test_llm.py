# tests/test_pipeline/test_llm.py
from unittest.mock import patch
from llama_index.core import Settings
import autoso.pipeline.llm as llm_module


def _reset_llm_cache():
    """Reset the module-level configured flag so tests don't interfere."""
    llm_module._configured = False


def test_configure_llm_uses_ollama_when_flag_set():
    _reset_llm_cache()
    with patch("autoso.config.USE_OLLAMA", True), \
         patch("autoso.config.OLLAMA_MODEL", "llama3.2"):
        from autoso.pipeline.llm import configure_llm
        llm = configure_llm()
        from llama_index.llms.ollama import Ollama
        assert isinstance(llm, Ollama)
        assert Settings.llm is llm
        assert Settings.embed_model is not None


def test_configure_llm_uses_anthropic_when_flag_unset():
    _reset_llm_cache()
    with patch("autoso.config.USE_OLLAMA", False), \
         patch("autoso.config.CLAUDE_MODEL", "claude-sonnet-4-6"), \
         patch("autoso.config.ANTHROPIC_API_KEY", "test-key"):
        from autoso.pipeline.llm import configure_llm
        llm = configure_llm()
        from llama_index.llms.anthropic import Anthropic
        assert isinstance(llm, Anthropic)
        assert Settings.llm is llm
        assert Settings.embed_model is not None


def test_configure_llm_sets_huggingface_embeddings():
    _reset_llm_cache()
    with patch("autoso.config.USE_OLLAMA", True), \
         patch("autoso.config.OLLAMA_MODEL", "llama3.2"):
        from autoso.pipeline.llm import configure_llm
        configure_llm()
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding
        assert isinstance(Settings.embed_model, HuggingFaceEmbedding)
