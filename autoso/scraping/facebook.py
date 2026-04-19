import asyncio
import re
from datetime import datetime, timezone
from typing import List

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

from autoso.scraping.models import Comment, Post, ScrapeError
from autoso.scraping.playwright_base import PlaywrightScraper


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
                platform="facebook",
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
                "[data-ad-comet-preview='message'], [data-testid='post_message']"
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
            return (await el.get_attribute("content")) or "Facebook"
        except Exception:
            return "Facebook"

    async def _extract_post_author(self, page) -> str | None:
        try:
            el = page.locator("h3 a, h2 a").first
            if await el.is_visible(timeout=2000):
                return (await el.inner_text()).strip() or None
        except Exception:
            pass
        return None

    async def _extract_post_date(self, page) -> datetime | None:
        try:
            el = page.locator("abbr[data-utime], time[datetime]").first
            if await el.is_visible(timeout=2000):
                ts = await el.get_attribute("datetime")
                if ts:
                    return datetime.fromisoformat(ts.replace("Z", "+00:00"))
                utime = await el.get_attribute("data-utime")
                if utime:
                    return datetime.fromtimestamp(int(utime), tz=timezone.utc)
        except Exception:
            pass
        return None

    async def _extract_post_likes(self, page) -> int | None:
        try:
            el = page.locator("[aria-label*='reaction']").first
            if await el.is_visible(timeout=2000):
                label = (await el.get_attribute("aria-label")) or ""
                m = re.search(r"[\d,]+", label)
                if m:
                    return int(m.group().replace(",", ""))
        except Exception:
            pass
        return None

    async def _expand_comments(self, page) -> None:
        try:
            sort_btn = page.get_by_text(re.compile(r"Most relevant", re.I)).first
            if await sort_btn.is_visible(timeout=3000):
                await sort_btn.click()
                await self._human_delay(500, 1000)
                all_btn = page.get_by_text(re.compile(r"All comments", re.I)).first
                if await all_btn.is_visible(timeout=3000):
                    await all_btn.click()
                    await self._human_delay(3000, 4000)
        except Exception:
            pass

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
                    await page.mouse.move(
                        box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
                    )
                    await page.mouse.wheel(0, 3000)
            except Exception:
                pass
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
        articles = page.locator("[aria-label^='Comment by']")
        count = await articles.count()
        top_level: List[Comment] = []
        position = 0

        for i in range(count):
            article = articles.nth(i)
            is_reply = await article.evaluate(
                "el => !!el.parentElement && !!el.parentElement.closest('[aria-label^=\"Comment by\"]')"
            )
            if is_reply:
                continue

            parent_comment = await self._build_comment(article, position, is_subcomment=False)
            if parent_comment is None:
                continue

            nested = article.locator("[aria-label^='Comment by']")
            nested_count = await nested.count()
            sub_pos = 0
            for j in range(nested_count):
                nested_article = nested.nth(j)
                sub = await self._build_comment(nested_article, sub_pos, is_subcomment=True)
                if sub is not None:
                    parent_comment.subcomments.append(sub)
                    sub_pos += 1

            top_level.append(parent_comment)
            position += 1

        return top_level

    async def _build_comment(
        self, article, position: int, is_subcomment: bool
    ) -> Comment | None:
        try:
            label = (await article.get_attribute("aria-label")) or ""
            author_match = re.match(r"Comment by (.+)", label)
            author = author_match.group(1).strip() if author_match else None

            spans = article.locator("span[dir='auto']")
            text = ""
            if await spans.count() >= 2:
                text = (await spans.nth(1).inner_text()).strip()
            if not text:
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
                return None

            date = None
            try:
                time_el = article.locator("abbr[data-utime], time[datetime]").first
                if await time_el.is_visible(timeout=300):
                    ts = await time_el.get_attribute("datetime")
                    if ts:
                        date = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    else:
                        utime = await time_el.get_attribute("data-utime")
                        if utime:
                            date = datetime.fromtimestamp(int(utime), tz=timezone.utc)
            except Exception:
                pass

            likes: int | None = None
            try:
                like_el = article.locator("[aria-label*='reaction']").first
                if await like_el.is_visible(timeout=300):
                    like_label = (await like_el.get_attribute("aria-label")) or ""
                    m = re.search(r"[\d,]+", like_label)
                    if m:
                        likes = int(m.group().replace(",", ""))
            except Exception:
                pass

            synth_id = f"fb_{'r_' if is_subcomment else ''}{position}"
            return Comment(
                id=synth_id,
                platform="facebook",
                author=author,
                date=date,
                text=text,
                likes=likes,
                position=position,
            )
        except Exception:
            return None


def _derive_id(url: str) -> str:
    m = re.search(r"/(\d{5,})", url)
    if m:
        return f"fb_{m.group(1)}"
    return f"fb_{abs(hash(url)) % 10_000_000_000}"
