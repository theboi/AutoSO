# autoso/diagnostics/telegram.py
"""Verify that the Telegram bot token is valid by calling getMe().

Usage:
    python -m autoso.diagnostics.telegram
"""
import json
import sys


def run() -> dict:
    """Call Telegram getMe() and return a result dict.

    Returns:
        {"ok": True, "username": "...", "id": N, "first_name": "..."}
        {"ok": False, "error": "..."}
    """
    import asyncio
    from telegram import Bot
    import autoso.config as config

    async def _get_me():
        async with Bot(token=config.TELEGRAM_TOKEN) as bot:
            return await bot.get_me()

    try:
        me = asyncio.run(_get_me())
        return {
            "ok": True,
            "username": me.username,
            "id": me.id,
            "first_name": me.first_name,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)
