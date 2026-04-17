import asyncio
from typing import List
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from autoso.scraping.playwright_base import PlaywrightScraper
from autoso.scraping.models import Comment, Post, ScrapeError


async def stealth_async(page):
    """Apply stealth evasion to a Playwright page."""
    stealth = Stealth()
    await stealth.apply_stealth_async(page)


class InstagramScraper(PlaywrightScraper):
    def __init__(self):
        super().__init__("instagram")

    def scrape(self, url: str) -> Post:
        return asyncio.run(self._scrape_async(url))

    async def _scrape_async(self, url: str) -> Post:
        async with async_playwright() as p:
            browser = await p.chromium.launch(**self._launch_kwargs())
            context = await self._get_context(browser)
            page = await context.new_page()
            await stealth_async(page)

            try:
                await page.goto(url, wait_until="networkidle", timeout=30_000)
            except Exception as exc:
                raise ScrapeError(f"Page load failed: {exc}", cause="timeout")

            await self._human_delay(1000, 3000)

            if "/accounts/login" in page.url:
                raise ScrapeError(
                    f"Login wall detected — session cookies may be expired for {url}",
                    cause="auth_wall",
                )

            post_content = await self._extract_post_content(page)
            post_title = await self._extract_post_title(page, url)
            await self._expand_comments(page)
            comments = await self._extract_comments(page)

            await self._save_session(context)
            await browser.close()

            return Post(
                title=post_title,
                content=post_content,
                url=url,
                platform="instagram",
                comments=comments,
            )

    async def _extract_post_content(self, page) -> str:
        try:
            el = page.locator(
                "article h1, article div[data-testid='post-content'], article span"
            ).first
            return await el.inner_text(timeout=5000)
        except Exception:
            return ""

    async def _extract_post_title(self, page, url: str) -> str:
        try:
            el = page.locator("meta[property='og:title']")
            return await el.get_attribute("content") or url
        except Exception:
            return url

    async def _expand_comments(self, page) -> None:
        for _ in range(20):
            try:
                btn = page.get_by_text("Load more comments").first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await self._human_delay(800, 1500)
                else:
                    break
            except Exception:
                break

    async def _extract_comments(self, page) -> List[Comment]:
        els = page.locator("article ul li span[dir='auto']")
        count = await els.count()
        comments = []
        for i in range(count):
            try:
                text = (await els.nth(i).inner_text()).strip()
                if len(text) > 10 and not text.lower().startswith("view"):
                    comments.append(
                        Comment(
                            platform="instagram",
                            text=text,
                            comment_id=f"ig_{i}",
                            position=i,
                        )
                    )
            except Exception:
                continue
        return comments
