import asyncio
import json
import random
from pathlib import Path
from playwright.async_api import async_playwright, Browser, BrowserContext
import autoso.config as config

SESSION_DIR = Path(__file__).parent.parent.parent / "data" / "sessions"


class PlaywrightScraper:
    def __init__(self, platform: str):
        self.platform = platform
        self._session_file = SESSION_DIR / f"{platform}_session.json"
        SESSION_DIR.mkdir(parents=True, exist_ok=True)

    def _launch_kwargs(self) -> dict:
        """Build kwargs for browser.launch(), including proxy if configured."""
        kwargs: dict = {"headless": True}
        if config.PROXY_URL:
            kwargs["proxy"] = {"server": config.PROXY_URL}
        return kwargs

    async def _get_context(self, browser: Browser) -> BrowserContext:
        storage_state = None
        if self._session_file.exists():
            with open(self._session_file) as f:
                storage_state = json.load(f)

        return await browser.new_context(
            storage_state=storage_state,
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            timezone_id="Asia/Singapore",
        )

    async def _save_session(self, context: BrowserContext) -> None:
        state = await context.storage_state()
        with open(self._session_file, "w") as f:
            json.dump(state, f)

    async def _human_delay(self, min_ms: int = 500, max_ms: int = 2000) -> None:
        await asyncio.sleep(random.uniform(min_ms, max_ms) / 1000)
