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
