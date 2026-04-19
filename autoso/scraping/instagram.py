import asyncio
import re
from datetime import datetime
from typing import List

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

from autoso.scraping.models import Comment, Post, ScrapeError
from autoso.scraping.playwright_base import PlaywrightScraper


async def stealth_async(page):
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
            page_title = await self._extract_page_title(page)
            post_author = await self._extract_post_author(page)
            post_date = await self._extract_post_date(page)
            post_likes = await self._extract_post_likes(page)
            await self._expand_comments(page)
            comments = await self._extract_comments(page)

            await self._save_session(context)
            await browser.close()

            return Post(
                id=_derive_id(url),
                platform="instagram",
                url=url,
                page_title=page_title,
                post_title=post_title,
                date=post_date,
                author=post_author,
                content=post_content,
                likes=post_likes,
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
            return (await el.get_attribute("content")) or url
        except Exception:
            return url

    async def _extract_page_title(self, page) -> str:
        try:
            el = page.locator("meta[property='og:site_name']")
            return (await el.get_attribute("content")) or "Instagram"
        except Exception:
            return "Instagram"

    async def _extract_post_author(self, page) -> str | None:
        try:
            el = page.locator("article header a").first
            if await el.is_visible(timeout=2000):
                return (await el.inner_text()).strip() or None
        except Exception:
            pass
        return None

    async def _extract_post_date(self, page) -> datetime | None:
        try:
            el = page.locator("article time[datetime]").first
            if await el.is_visible(timeout=2000):
                ts = await el.get_attribute("datetime")
                if ts:
                    return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            pass
        return None

    async def _extract_post_likes(self, page) -> int | None:
        try:
            el = page.locator("section button span").first
            if await el.is_visible(timeout=2000):
                txt = (await el.inner_text()).replace(",", "")
                m = re.search(r"\d+", txt)
                if m:
                    return int(m.group())
        except Exception:
            pass
        return None

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
        comments: List[Comment] = []
        position = 0
        for i in range(count):
            try:
                text = (await els.nth(i).inner_text()).strip()
                if len(text) <= 10 or text.lower().startswith("view"):
                    continue
                comments.append(
                    Comment(
                        id=f"ig_{i}",
                        platform="instagram",
                        author=None,
                        date=None,
                        text=text,
                        likes=None,
                        position=position,
                    )
                )
                position += 1
            except Exception:
                continue
        return comments


def _derive_id(url: str) -> str:
    m = re.search(r"/p/([A-Za-z0-9_-]+)", url)
    if m:
        return f"ig_{m.group(1)}"
    return f"ig_{abs(hash(url)) % 10_000_000_000}"
