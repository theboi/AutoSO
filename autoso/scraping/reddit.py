from __future__ import annotations

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


class RedditScraper(PlaywrightScraper):
    def __init__(self):
        super().__init__("reddit")

    def scrape(self, url: str) -> Post:
        return asyncio.run(self._scrape_async(url))

    async def _scrape_async(self, url: str) -> Post:
        old_url = _to_old_reddit(url)

        async with async_playwright() as p:
            browser = await p.chromium.launch(**self._launch_kwargs())
            context = await self._get_context(browser)
            page = await context.new_page()
            await stealth_async(page)

            try:
                resp = await page.goto(old_url, wait_until="domcontentloaded", timeout=30_000)
            except Exception as exc:
                raise ScrapeError(f"Page load failed: {exc}", cause="timeout")

            if resp and resp.status == 403:
                raise ScrapeError(
                    "Reddit blocked this request (403). "
                    "Set PROXY_URL to a residential/ISP proxy in .env to bypass this.",
                    cause="auth_wall",
                )

            await self._human_delay(800, 1500)

            title_el = page.locator("#siteTable .link .title a.title, h1").first
            post_title = ""
            try:
                post_title = (await title_el.inner_text(timeout=5000)).strip()
            except Exception:
                pass

            subreddit = ""
            try:
                sub_el = page.locator(".sidecontentbox a[href*='/r/'], .redditname a").first
                if await sub_el.is_visible(timeout=2000):
                    subreddit = (await sub_el.inner_text()).strip()
            except Exception:
                pass
            if not subreddit:
                m = re.search(r"reddit\.com(/r/[^/]+)", old_url)
                subreddit = m.group(1) if m else "reddit"

            post_author = None
            try:
                author_el = page.locator(".tagline .author").first
                if await author_el.is_visible(timeout=2000):
                    post_author = (await author_el.inner_text()).strip() or None
            except Exception:
                pass

            post_date = None
            try:
                time_el = page.locator(".tagline time").first
                if await time_el.is_visible(timeout=2000):
                    ts = await time_el.get_attribute("datetime")
                    if ts:
                        post_date = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                pass

            post_score = None
            try:
                score_el = page.locator(".score.unvoted").first
                if await score_el.is_visible(timeout=2000):
                    txt = (await score_el.inner_text()).replace(",", "").strip()
                    post_score = int(txt) if txt.lstrip("-").isdigit() else None
            except Exception:
                pass

            post_content = ""
            try:
                body_el = page.locator(".expando .usertext-body .md").first
                if await body_el.is_visible(timeout=2000):
                    post_content = (await body_el.inner_text()).strip()
            except Exception:
                pass
            if not post_content:
                post_content = post_title

            await self._expand_comments(page)
            comments = await self._extract_comments(page)

            await self._save_session(context)
            await browser.close()

            return Post(
                id=_derive_id(url),
                platform="reddit",
                url=url,
                page_title=subreddit,
                post_title=post_title,
                date=post_date,
                author=post_author,
                content=post_content,
                likes=post_score,
                comments=comments,
            )

    async def _expand_comments(self, page) -> None:
        for _ in range(20):
            try:
                more = page.locator("span.morecomments a").first
                if await more.is_visible(timeout=1000):
                    await more.click()
                    await self._human_delay(800, 1500)
                else:
                    break
            except Exception:
                break

    async def _extract_comments(self, page) -> List[Comment]:
        top_level = page.locator(".commentarea > .sitetable > .thing.comment")
        count = await top_level.count()
        result: List[Comment] = []
        for i in range(count):
            comment = await self._build_comment(top_level.nth(i), i)
            if comment:
                result.append(comment)
        return result

    async def _build_comment(self, el, position: int) -> Comment | None:
        try:
            if "deleted" in (await el.get_attribute("class") or ""):
                return None

            author = None
            try:
                a_el = el.locator(".entry .author").first
                if await a_el.is_visible(timeout=500):
                    author = (await a_el.inner_text()).strip() or None
            except Exception:
                pass

            text = ""
            try:
                body = el.locator(".entry .usertext-body .md").first
                text = (await body.inner_text(timeout=2000)).strip()
            except Exception:
                pass

            if not text or text in ("[deleted]", "[removed]"):
                return None

            date = None
            try:
                t = el.locator(".entry time").first
                if await t.is_visible(timeout=500):
                    ts = await t.get_attribute("datetime")
                    if ts:
                        date = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                pass

            score = None
            try:
                s = el.locator(".entry .score.unvoted").first
                if await s.is_visible(timeout=500):
                    txt = (await s.inner_text()).replace(",", "").strip()
                    score = int(txt) if txt.lstrip("-").isdigit() else None
            except Exception:
                pass

            subcomments: List[Comment] = []
            child_els = el.locator(".child .sitetable > .thing.comment")
            child_count = await child_els.count()
            for j in range(child_count):
                sub = await self._build_comment(child_els.nth(j), j)
                if sub:
                    subcomments.append(sub)

            return Comment(
                id=f"rd_{position}",
                platform="reddit",
                author=author,
                date=date,
                text=text,
                likes=score,
                position=position,
                subcomments=subcomments,
            )
        except Exception:
            return None


def _to_old_reddit(url: str) -> str:
    url = re.sub(r"https?://(www\.)?reddit\.com", "https://old.reddit.com", url)
    if not url.rstrip("/").endswith("?limit=500"):
        url = url.rstrip("/") + "?limit=500"
    return url


def _derive_id(url: str) -> str:
    m = re.search(r"/comments/([a-z0-9]+)", url)
    if m:
        return f"rd_{m.group(1)}"
    return f"rd_{abs(hash(url)) % 10_000_000_000}"
