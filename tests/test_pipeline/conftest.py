# tests/test_pipeline/conftest.py
import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True, scope="session")
def configure_pipeline_llm():
    """Configure embeddings for all pipeline tests."""
    import autoso.pipeline.llm as llm_module
    llm_module._configured = False
    with patch("autoso.config.USE_OLLAMA", True), patch("autoso.config.OLLAMA_MODEL", "llama3.2"):
        from autoso.pipeline.llm import configure_llm
        configure_llm()
    yield
