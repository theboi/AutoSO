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
