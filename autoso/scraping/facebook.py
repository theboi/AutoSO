import asyncio
import re
from typing import List
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from autoso.scraping.playwright_base import PlaywrightScraper
from autoso.scraping.models import Comment, Post, ScrapeError


async def stealth_async(page):
    """Apply stealth evasion to a Playwright page."""
    stealth = Stealth()
    await stealth.apply_stealth_async(page)


class FacebookScraper(PlaywrightScraper):
    def __init__(self):
        super().__init__("facebook")

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

            if "/login" in page.url or "must log in" in (await page.content()).lower():
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
                platform="facebook",
                comments=comments,
            )

    async def _extract_post_content(self, page) -> str:
        try:
            el = page.locator(
                "[data-ad-comet-preview='message'], [data-testid='post_message']"
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
        # Switch from "Most relevant" to "All comments" so every top-level comment is eligible
        try:
            sort_btn = page.get_by_text(re.compile(r"Most relevant", re.I)).first
            if await sort_btn.is_visible(timeout=3000):
                await sort_btn.click()
                await self._human_delay(500, 1000)
                all_btn = page.get_by_text(re.compile(r"All comments", re.I)).first
                if await all_btn.is_visible(timeout=3000):
                    await all_btn.click()
                    await self._human_delay(3000, 4000)  # wait for re-render
        except Exception:
            pass

        # Scroll down to load more comments via Facebook's intersection observers.
        # We first try scrolling the comments' scrollable ancestor (an overflow div),
        # then fall back to mouse-wheel events on the last comment element.
        _SCROLL_JS = """() => {
            const comment = document.querySelector('[aria-label^="Comment by"]');
            if (!comment) { window.scrollTo(0, document.body.scrollHeight); return; }
            let el = comment.parentElement;
            while (el && el !== document.body) {
                const s = window.getComputedStyle(el);
                if (s.overflowY === 'auto' || s.overflowY === 'scroll') {
                    el.scrollTop = el.scrollHeight;
                    return;
                }
                el = el.parentElement;
            }
            window.scrollTo(0, document.body.scrollHeight);
        }"""
        reply_pattern = re.compile(r"View (all \d+|\d+) repl", re.I)
        prev_count = -1
        stable = 0
        for _ in range(80):
            comments_loc = page.locator("[aria-label^='Comment by']")
            current_count = await comments_loc.count()
            if current_count == prev_count:
                stable += 1
                if stable >= 3:
                    break
            else:
                stable = 0
            prev_count = current_count
            await page.evaluate(_SCROLL_JS)
            try:
                box = await comments_loc.last.bounding_box()
                if box:
                    await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                    await page.mouse.wheel(0, 3000)
            except Exception:
                pass
            # Expand any reply threads visible so far (interleaved with scrolling)
            for _ in range(5):
                try:
                    btn = page.get_by_text(reply_pattern).first
                    if await btn.is_visible(timeout=500):
                        await btn.click()
                        await self._human_delay(400, 700)
                    else:
                        break
                except Exception:
                    break
            await self._human_delay(2000, 3000)

        # Final sweep: expand any reply threads that loaded after the last scroll
        for _ in range(80):
            try:
                btn = page.get_by_text(reply_pattern).first
                if await btn.is_visible(timeout=800):
                    await btn.click()
                    await self._human_delay(400, 700)
                else:
                    break
            except Exception:
                break

    async def _extract_comments(self, page) -> List[Comment]:
        # Each comment lives in [role='article'][aria-label^='Comment by'].
        # span[dir='auto'][0] = commenter name, span[dir='auto'][1] = comment text.
        articles = page.locator("[aria-label^='Comment by']")
        count = await articles.count()
        comments = []
        position = 0
        for i in range(count):
            try:
                article = articles.nth(i)
                spans = article.locator("span[dir='auto']")
                text = ""
                if await spans.count() >= 2:
                    text = (await spans.nth(1).inner_text()).strip()
                if not text:
                    # Sticker/image-only comment — describe the image
                    imgs = article.locator("img[alt]")
                    img_count = await imgs.count()
                    descs = []
                    for j in range(img_count):
                        alt = (await imgs.nth(j).get_attribute("alt") or "").strip()
                        if alt:
                            descs.append(alt)
                    if descs:
                        text = f"sticker: {', '.join(descs)}"
                if not text:
                    continue
                comments.append(
                    Comment(
                        platform="facebook",
                        text=text,
                        comment_id=f"fb_{i}",
                        position=position,
                    )
                )
                position += 1
            except Exception:
                continue
        return comments
