import asyncio
import re
from datetime import datetime, timezone
from typing import Any, List

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

from autoso.scraping.models import Comment, Post, ScrapeError
from autoso.scraping.playwright_base import PlaywrightScraper


async def stealth_async(page):
    stealth = Stealth()
    await stealth.apply_stealth_async(page)


_COMMENT_API_PATTERN = re.compile(r"/api/comment/list", re.I)


class TikTokScraper(PlaywrightScraper):
    def __init__(self):
        super().__init__("tiktok")

    def scrape(self, url: str) -> Post:
        return asyncio.run(self._scrape_async(url))

    async def _scrape_async(self, url: str) -> Post:
        captured_payloads: list[dict[str, Any]] = []

        async def on_response(response):
            if _COMMENT_API_PATTERN.search(response.url):
                try:
                    captured_payloads.append(await response.json())
                except Exception:
                    pass

        async with async_playwright() as p:
            browser = await p.chromium.launch(**self._launch_kwargs())
            context = await self._get_context(browser)
            page = await context.new_page()
            await stealth_async(page)
            page.on("response", lambda r: asyncio.ensure_future(on_response(r)))

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            except Exception as exc:
                raise ScrapeError(f"Page load failed: {exc}", cause="timeout")

            await self._human_delay(1500, 2500)

            content = await page.content()
            if "captcha" in content.lower() or (
                ("log in" in content.lower() or "sign up" in content.lower())
                and "Make Your Day" in await page.title()
            ):
                raise ScrapeError(
                    "TikTok login/CAPTCHA wall — session cookies expired. "
                    "Delete data/sessions/tiktok_session.json, log in via a real browser, "
                    "then export cookies using 'Get cookies.txt LOCALLY' extension.",
                    cause="auth_wall",
                )

            await self._scroll_comments(page)
            await self._human_delay(2000, 4000)

            post_title = await self._extract_caption(page)
            author = await self._extract_author(page)
            page_title = f"@{author}" if author else "TikTok"
            post_date = await self._extract_post_date(page)
            post_likes = await self._extract_post_likes(page)

            all_comments: List[Comment] = []
            for payload in captured_payloads:
                all_comments.extend(
                    _extract_from_payload(payload, start_position=len(all_comments))
                )

            await self._save_session(context)
            await browser.close()

            return Post(
                id=_derive_id(url),
                platform="tiktok",
                url=url,
                page_title=page_title,
                post_title=post_title,
                date=post_date,
                author=author,
                content=post_title,
                likes=post_likes,
                comments=all_comments,
            )

    async def _scroll_comments(self, page) -> None:
        for _ in range(30):
            try:
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
            except Exception:
                break
            await self._human_delay(800, 1500)

    async def _extract_caption(self, page) -> str:
        try:
            el = page.locator("meta[property='og:title']")
            return (await el.get_attribute("content")) or ""
        except Exception:
            return ""

    async def _extract_author(self, page) -> str | None:
        try:
            el = page.locator("a[data-e2e='browse-username'], h3").first
            if await el.is_visible(timeout=2000):
                txt = (await el.inner_text()).strip().lstrip("@")
                return txt or None
        except Exception:
            pass
        return None

    async def _extract_post_date(self, page) -> datetime | None:
        try:
            el = page.locator("span[data-e2e='browser-nickname'] + span").first
            if await el.is_visible(timeout=2000):
                txt = (await el.inner_text()).strip()
                try:
                    return datetime.fromisoformat(txt).replace(tzinfo=timezone.utc)
                except ValueError:
                    return None
        except Exception:
            pass
        return None

    async def _extract_post_likes(self, page) -> int | None:
        try:
            el = page.locator("strong[data-e2e='like-count']").first
            if await el.is_visible(timeout=2000):
                txt = (await el.inner_text()).strip().upper().replace(",", "")
                return _parse_count(txt)
        except Exception:
            pass
        return None


def _extract_from_payload(payload: dict[str, Any], start_position: int) -> list[Comment]:
    raw = payload.get("comments") or []
    out: list[Comment] = []
    for i, rc in enumerate(raw):
        pos = start_position + i
        subs = []
        for j, rr in enumerate(rc.get("reply_comment") or []):
            subs.append(
                Comment(
                    id=str(rr.get("cid", "")),
                    platform="tiktok",
                    author=rr.get("nickname"),
                    date=_epoch_to_dt(rr.get("create_time")),
                    text=rr.get("text", ""),
                    likes=rr.get("digg_count"),
                    position=j,
                )
            )
        out.append(
            Comment(
                id=str(rc.get("cid", "")),
                platform="tiktok",
                author=rc.get("nickname"),
                date=_epoch_to_dt(rc.get("create_time")),
                text=rc.get("text", ""),
                likes=rc.get("digg_count"),
                position=pos,
                subcomments=subs,
            )
        )
    return out


def _parse_count(txt: str) -> int | None:
    m = re.match(r"^([\d.]+)([KMB])?$", txt)
    if not m:
        try:
            return int(txt)
        except ValueError:
            return None
    n = float(m.group(1))
    suf = m.group(2)
    mult = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(suf, 1)
    return int(n * mult)


def _epoch_to_dt(epoch: float | None) -> datetime | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc)


def _derive_id(url: str) -> str:
    m = re.search(r"/video/(\d+)", url)
    if m:
        return f"tt_{m.group(1)}"
    return f"tt_{abs(hash(url)) % 10_000_000_000}"
