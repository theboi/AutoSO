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

    import autoso.config as cfg
    importlib.reload(cfg)
    assert cfg.WHITELISTED_USER_IDS == {111, 222, 333}

def test_empty_whitelist_gives_empty_set(monkeypatch):
    monkeypatch.setenv("WHITELISTED_USER_IDS", "")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tok")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
    monkeypatch.setenv("SUPABASE_URL", "http://x")
    monkeypatch.setenv("SUPABASE_KEY", "k")

    import autoso.config as cfg
    importlib.reload(cfg)
    assert cfg.WHITELISTED_USER_IDS == set()
