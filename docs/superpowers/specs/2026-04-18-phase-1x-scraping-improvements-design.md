# Phase 1X: Scraping Improvements Design

**Date:** 2026-04-18
**Status:** Approved

## Overview

Phase 1X improves the scraping layer in three sequential steps:

1. **Step 1** — New `Post`/`Comment` data model + `scrapes` Supabase table
2. **Step 2** — Reddit rewrite (drop PRAW, use JSON API) + update existing FB/IG scrapers to new model
3. **Step 3** — Three new scrapers: HardwareZone, YouTube, TikTok

---

## Step 1: Data Model & Supabase Schema

### Models (`autoso/scraping/models.py`)

Replace current flat dataclasses with:

```python
@dataclass
class Comment:
    id: str                          # platform-specific or synthetic (e.g. "fb_42")
    platform: str
    author: str | None               # None if unextractable
    date: datetime | None            # None if unextractable
    text: str
    likes: int | None                # None if unextractable
    position: int                    # 0-indexed, top-level ordering only
    subcomments: list[Comment] = field(default_factory=list)

@dataclass
class Post:
    id: str                          # URL-derived or platform post ID
    platform: str
    url: str
    page_title: str                  # e.g. "MINDEF Singapore | Facebook"
    post_title: str                  # og:title or thread title
    date: datetime | None
    author: str | None
    content: str | None
    likes: int | None                # None if unextractable
    comments: list[Comment] = field(default_factory=list)
```

`ScrapeError` is unchanged.

`position` tracks top-level comment order only. Replies in `subcomments` do not have independent positions.

Both models get `to_dict()` / `from_dict()` methods for JSON round-tripping through Supabase. `datetime` fields serialize as ISO 8601 strings.

### Supabase Migration (`migrations/003_scrapes_table.sql`)

```sql
TRUNCATE TABLE citations, analyses RESTART IDENTITY CASCADE;

CREATE TABLE scrapes (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    url        TEXT        NOT NULL,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    result     JSONB       NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scrapes_url_scraped_at
    ON scrapes (url, scraped_at DESC);

ALTER TABLE analyses
    ADD COLUMN scrape_id UUID REFERENCES scrapes(id);
```

### Storage (`autoso/storage/supabase.py`)

`store_result()` gains a required `scrape_id: str` parameter. Every new analysis must reference a scrape.

Two new functions:

```python
def get_recent_scrape(url: str) -> tuple[str, Post] | None:
    # Query scrapes where url = ? and scraped_at > NOW() - INTERVAL '30 minutes'
    # Order by scraped_at DESC, limit 1
    # Returns (scrape_id, Post) if hit, else None

def store_scrape(url: str, post: Post) -> str:
    # Insert into scrapes (url, result=post.to_dict())
    # Returns the new scrape_id UUID
```

---

## Step 2: Scraper Dispatch & Platform Updates

### Unified Entry Point (`autoso/scraping/__init__.py`)

```python
def scrape(url: str) -> tuple[str, Post]:
    # 1. get_recent_scrape(url) → return (scrape_id, post) if cache hit
    # 2. Route to platform scraper by URL pattern
    # 3. store_scrape(url, post) → scrape_id
    # 4. Return (scrape_id, post)
```

Returns `(scrape_id, Post)` so callers can pass `scrape_id` directly to `store_result()`.

Platform routing:

| URL pattern | Scraper |
|---|---|
| `facebook.com` | `FacebookScraper` |
| `instagram.com` | `InstagramScraper` |
| `reddit.com` | `RedditScraper` (rewritten) |
| `hardwarezone.com.sg` | `HardwareZoneScraper` (new) |
| `youtube.com`, `youtu.be` | `YouTubeScraper` (new) |
| `tiktok.com` | `TikTokScraper` (new) |

### Reddit Rewrite (`autoso/scraping/reddit.py`)

Drop PRAW entirely. Remove `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT` from config.

Append `.json` to the Reddit post URL and fetch with `httpx` (or `requests`). The response is a two-element list: `[post_data, comments_data]`.

- `post_data[0].data.children[0].data` → post fields (title, selftext, author, score, created_utc)
- `comments_data[0].data.children` → recursive comment tree

Map recursively: each comment → `Comment`, with `replies.data.children` → `subcomments`. Skip `kind == "more"` nodes. Skip deleted/removed bodies. No Playwright required.

### Facebook & Instagram Updates

Update `_extract_comments()` in both scrapers to populate the new `Comment` fields:

- `author` — extract from `aria-label="Comment by <name>"` (FB) or username span (IG)
- `date` — extract from `<abbr>` or `<time>` elements; parse to `datetime`; `None` on failure
- `likes` — extract reaction count element; `None` on failure
- `subcomments` — Facebook already expands reply threads during `_expand_comments()`; after extraction, detect reply articles nested inside parent articles and attach as `subcomments` rather than flat comments. Instagram replies are not easily distinguishable from top-level — `subcomments` stays empty.

All fields are best-effort: `None` / `0` / `""` on extraction failure, never raises.

### Pipeline Compatibility

The pipeline consumes comments as a flat text corpus for LlamaIndex. Add a helper in `autoso/scraping/__init__.py`:

```python
def flatten_comments(post: Post) -> list[Comment]:
    # Returns all top-level comments + all subcomments recursively in order
```

Pipeline switches from `post.comments` to `flatten_comments(post)`.

---

## Step 3: New Scrapers

### HardwareZone (`autoso/scraping/hardwarezone.py`)

Playwright + stealth, same pattern as FB/IG.

- `page_title` — forum section name
- `post_title` — thread title
- `content` — body of the first post
- Top-level comments — subsequent posts (no nesting; `subcomments` always empty)
- `author`, `date`, `likes` — extracted from post metadata per row
- **Pagination** — detect "Next page" link, follow until absent. ~20 comments per page. Collect all pages before returning.

### YouTube (`autoso/scraping/youtube.py`)

Uses `yt-dlp` via `subprocess` (independent of transcription downloader — same tool, different flags):

```bash
yt-dlp --skip-download --write-info-json --write-comments --no-warnings -o "%(id)s" <url>
```

Outputs a `<video_id>.info.json` file containing video metadata and a `comments` array. Each comment has `id`, `author`, `text`, `timestamp`, `like_count`, `parent` (ID of parent comment or `"root"`).

Map: comments where `parent == "root"` → top-level `Comment`; others → attached to parent's `subcomments`.

- `page_title` — channel name
- `post_title` — video title
- `content` — video description
- `date` — video upload date
- `author` — channel name
- `likes` — video like count

### TikTok (`autoso/scraping/tiktok.py`)

Playwright + stealth. Intercept XHR responses matching `/api/comment/list/` using `page.on("response", ...)` to capture structured comment JSON directly from the network, rather than scraping the DOM.

Each intercepted payload contains comments with `cid`, `nickname`, `create_time`, `digg_count`, `text`, and `reply_comment` array for nested replies.

- `page_title` — `@username` handle
- `post_title` — video caption
- `content` — same as post_title (TikTok has no separate body)
- `author`, `date`, `likes` — from video metadata on page

---

## Field Extraction Summary

| Platform | author | date | likes | subcomments |
|---|---|---|---|---|
| Facebook | best-effort | best-effort | best-effort | yes (expanded) |
| Instagram | best-effort | best-effort | best-effort | always empty |
| Reddit | always | always | always (score) | yes (full tree) |
| HardwareZone | always | always | best-effort | always empty |
| YouTube | always | always | always | yes |
| TikTok | always | always | always | yes |

---

## Out of Scope

- Authentication refresh (cookie expiry handling) — existing behaviour unchanged
- Rate limiting / retry logic — existing behaviour unchanged
- Any changes to the pipeline, bot, or UI beyond `flatten_comments()` and `store_result()` signature
