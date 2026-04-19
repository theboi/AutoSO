import asyncio
import re
from datetime import datetime
from typing import List
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

from autoso.scraping.models import Comment, Post, ScrapeError
from autoso.scraping.playwright_base import PlaywrightScraper


async def stealth_async(page):
    stealth = Stealth()
    await stealth.apply_stealth_async(page)


class HardwareZoneScraper(PlaywrightScraper):
    def __init__(self):
        super().__init__("hardwarezone")

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

            page_title = await self._extract_page_title(page)
            post_title = await self._extract_thread_title(page)
            first_post = await self._extract_first_post(page)

            all_comments: list[Comment] = []
            comments_page_1 = await self._extract_comments_on_page(page, start_position=0)
            all_comments.extend(comments_page_1)
            position = len(all_comments)

            for _ in range(50):
                next_link = page.locator("a.pageNav-jump--next").first
                try:
                    if not await next_link.is_visible(timeout=2000):
                        break
                    href = await next_link.get_attribute("href")
                    if not href:
                        break
                except Exception:
                    break

                next_url = _resolve_url(url, href)
                try:
                    await page.goto(next_url, wait_until="networkidle", timeout=30_000)
                except Exception:
                    break
                await self._human_delay(800, 1500)
                page_comments = await self._extract_comments_on_page(
                    page, start_position=position
                )
                all_comments.extend(page_comments)
                position = len(all_comments)

            await self._save_session(context)
            await browser.close()

            return Post(
                id=_derive_id(url),
                platform="hardwarezone",
                url=url,
                page_title=page_title,
                post_title=post_title,
                date=first_post.get("date"),
                author=first_post.get("author"),
                content=first_post.get("text", ""),
                likes=first_post.get("likes"),
                comments=all_comments,
            )

    async def _extract_page_title(self, page) -> str:
        try:
            el = page.locator("meta[property='og:site_name']")
            return (await el.get_attribute("content")) or "HardwareZone"
        except Exception:
            return "HardwareZone"

    async def _extract_thread_title(self, page) -> str:
        try:
            el = page.locator("h1.p-title-value").first
            if await el.is_visible(timeout=2000):
                return (await el.inner_text()).strip()
        except Exception:
            pass
        return ""

    async def _extract_first_post(self, page) -> dict:
        try:
            msg = page.locator("article.message").first
            if not await msg.is_visible(timeout=2000):
                return {}
            text = await self._msg_text(msg)
            return {
                "text": text,
                "author": await self._msg_author(msg),
                "date": await self._msg_date(msg),
                "likes": await self._msg_likes(msg),
            }
        except Exception:
            return {}

    async def _extract_comments_on_page(self, page, start_position: int) -> List[Comment]:
        msgs = page.locator("article.message")
        count = await msgs.count()
        comments: List[Comment] = []
        skip_first = start_position == 0
        for i in range(count):
            if skip_first and i == 0:
                continue
            msg = msgs.nth(i)
            text = await self._msg_text(msg)
            if not text:
                continue
            comments.append(
                Comment(
                    id=f"hwz_{start_position + len(comments)}",
                    platform="hardwarezone",
                    author=await self._msg_author(msg),
                    date=await self._msg_date(msg),
                    text=text,
                    likes=await self._msg_likes(msg),
                    position=start_position + len(comments),
                )
            )
        return comments

    async def _msg_text(self, msg) -> str:
        try:
            body = msg.locator(".bbWrapper, .message-body").first
            return (await body.inner_text(timeout=2000)).strip()
        except Exception:
            return ""

    async def _msg_author(self, msg) -> str | None:
        try:
            el = msg.locator(".message-userDetails a.username, a.username").first
            if await el.is_visible(timeout=500):
                return (await el.inner_text()).strip() or None
        except Exception:
            pass
        return None

    async def _msg_date(self, msg) -> datetime | None:
        try:
            el = msg.locator("time[datetime]").first
            if await el.is_visible(timeout=500):
                ts = await el.get_attribute("datetime")
                if ts:
                    return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            pass
        return None

    async def _msg_likes(self, msg) -> int | None:
        try:
            el = msg.locator(".reactionsBar-link, .likesBar a").first
            if await el.is_visible(timeout=500):
                txt = (await el.inner_text()).replace(",", "")
                m = re.search(r"\d+", txt)
                if m:
                    return int(m.group())
        except Exception:
            pass
        return None


def _derive_id(url: str) -> str:
    m = re.search(r"\.(\d+)/?", url)
    if m:
        return f"hwz_{m.group(1)}"
    return f"hwz_{abs(hash(url)) % 10_000_000_000}"


def _resolve_url(base: str, href: str) -> str:
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        parts = urlparse(base)
        return f"{parts.scheme}://{parts.netloc}{href}"
    return urljoin(base, href)
