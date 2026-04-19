# AutoSO — Phase 1X: Scraping Improvements

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrich the scraping layer with a new `Post`/`Comment` data model (author, date, likes, nested replies), replace PRAW with Reddit's JSON API, add Supabase-backed scrape caching with a 30-minute freshness window, and add new scrapers for HardwareZone, YouTube, and TikTok.

**Architecture:** Three sequential steps:
1. Data model + Supabase `scrapes` table + storage helpers
2. Unified `scrape()` dispatch with caching; Reddit JSON rewrite; FB/IG model updates; pipeline integration
3. Three new scrapers (HardwareZone, YouTube, TikTok)

No backward compatibility — existing `analyses` and `citations` rows are truncated by the migration. The pipeline gains a `flatten_comments()` helper to consume the nested comment tree as a flat list.

**Tech Stack:** httpx (Reddit JSON API + HardwareZone), Playwright + playwright-stealth (FB, IG, HardwareZone, TikTok), yt-dlp (YouTube), Supabase Python client, existing pytest suite.

**Pre-requisite:** Design spec at `docs/superpowers/specs/2026-04-18-phase-1x-scraping-improvements-design.md`.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `autoso/scraping/models.py` | Rewrite | New `Post`/`Comment` dataclasses with `to_dict`/`from_dict` |
| `autoso/scraping/base.py` | Modify | Extend `detect_platform` + `get_scraper` for HardwareZone/YouTube/TikTok |
| `autoso/scraping/__init__.py` | Rewrite | `scrape(url) -> (scrape_id, Post)` with cache lookup; `flatten_comments(post)` helper |
| `autoso/scraping/reddit.py` | Rewrite | JSON API, no PRAW |
| `autoso/scraping/facebook.py` | Modify | Populate new Comment fields; nest replies in `subcomments` |
| `autoso/scraping/instagram.py` | Modify | Populate new Comment fields (subcomments stays empty) |
| `autoso/scraping/hardwarezone.py` | Create | Playwright thread scraper with pagination |
| `autoso/scraping/youtube.py` | Create | yt-dlp subprocess-based scraper |
| `autoso/scraping/tiktok.py` | Create | Playwright + XHR response interception |
| `autoso/storage/supabase.py` | Modify | Add `store_scrape`, `get_recent_scrape`; `store_result` gains required `scrape_id` |
| `autoso/pipeline/indexer.py` | Modify | Use `comment.id` (renamed from `comment.comment_id`) |
| `autoso/pipeline/citation.py` | Modify | `CitationNode.id` renamed from `comment_id`; metadata key update |
| `autoso/pipeline/pipeline.py` | Modify | Use `scrape()` + `flatten_comments()`; pass `scrape_id` to `store_result` |
| `autoso/config.py` | Modify | Remove `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT` |
| `pyproject.toml` | Modify | Remove `praw` |
| `migrations/003_scrapes_table.sql` | Create | Truncate old rows, create `scrapes`, add `scrape_id` to `analyses` |
| `tests/test_scraping/test_models.py` | Rewrite | Tests for new model + serialization |
| `tests/test_scraping/test_factory.py` | Rewrite | Platform detection for all 6 platforms |
| `tests/test_scraping/test_reddit.py` | Rewrite | JSON API mock tests |
| `tests/test_scraping/test_facebook.py` | Modify | Assert new fields populated |
| `tests/test_scraping/test_instagram.py` | Modify | Assert new fields populated |
| `tests/test_scraping/test_hardwarezone.py` | Create | Mocked pagination tests |
| `tests/test_scraping/test_youtube.py` | Create | Mocked subprocess tests |
| `tests/test_scraping/test_tiktok.py` | Create | Mocked XHR interception tests |
| `tests/test_scraping/test_dispatch.py` | Create | `scrape()` cache hit/miss + `flatten_comments` tests |
| `tests/test_storage/test_supabase.py` | Modify | `store_scrape`, `get_recent_scrape`, updated `store_result` tests |
| `tests/test_pipeline/test_indexer.py` | Modify | Update for new field names |
| `tests/test_pipeline/test_citation.py` | Modify | Update for new field names |
| `tests/test_pipeline/test_pipeline.py` | Modify | Patch `scrape()` instead of `get_scraper()`, pass mocked Post |

---

# Step 1: Data Model & Storage Foundation

## Task 1: New Post/Comment Dataclasses with Serialization

**Files:**
- Modify: `autoso/scraping/models.py`
- Modify: `tests/test_scraping/test_models.py`

- [ ] **Step 1: Rewrite `tests/test_scraping/test_models.py`**

```python
from datetime import datetime, timezone
from autoso.scraping.models import Comment, Post, ScrapeError


def test_comment_construction_with_all_fields():
    dt = datetime(2026, 4, 18, 10, 30, tzinfo=timezone.utc)
    c = Comment(
        id="fb_0",
        platform="facebook",
        author="Alice",
        date=dt,
        text="Hello",
        likes=5,
        position=0,
    )
    assert c.id == "fb_0"
    assert c.author == "Alice"
    assert c.date == dt
    assert c.likes == 5
    assert c.subcomments == []


def test_comment_optional_fields_default_to_none():
    c = Comment(
        id="x", platform="reddit", author=None, date=None,
        text="hi", likes=None, position=0,
    )
    assert c.author is None
    assert c.date is None
    assert c.likes is None


def test_comment_with_subcomments():
    reply = Comment(id="r1", platform="reddit", author="Bob", date=None,
                    text="reply", likes=1, position=0)
    parent = Comment(id="p1", platform="reddit", author="Alice", date=None,
                     text="parent", likes=2, position=0, subcomments=[reply])
    assert len(parent.subcomments) == 1
    assert parent.subcomments[0].text == "reply"


def test_post_construction_with_all_fields():
    dt = datetime(2026, 4, 18, 9, 0, tzinfo=timezone.utc)
    post = Post(
        id="fb_123",
        platform="facebook",
        url="https://facebook.com/mindef/posts/123",
        page_title="MINDEF Singapore | Facebook",
        post_title="NS Announcement",
        date=dt,
        author="MINDEF",
        content="Post body",
        likes=42,
        comments=[],
    )
    assert post.id == "fb_123"
    assert post.page_title == "MINDEF Singapore | Facebook"
    assert post.likes == 42
    assert post.comments == []


def test_comment_to_dict_round_trip():
    dt = datetime(2026, 4, 18, 10, 30, tzinfo=timezone.utc)
    reply = Comment(id="r1", platform="reddit", author="Bob", date=dt,
                    text="reply", likes=1, position=0)
    c = Comment(id="c1", platform="reddit", author="Alice", date=dt,
                text="parent", likes=5, position=0, subcomments=[reply])
    d = c.to_dict()
    assert d["id"] == "c1"
    assert d["date"] == "2026-04-18T10:30:00+00:00"
    assert d["subcomments"][0]["id"] == "r1"

    restored = Comment.from_dict(d)
    assert restored == c


def test_comment_from_dict_handles_null_date():
    d = {
        "id": "c1", "platform": "reddit", "author": None, "date": None,
        "text": "hi", "likes": None, "position": 0, "subcomments": [],
    }
    c = Comment.from_dict(d)
    assert c.date is None
    assert c.likes is None


def test_post_to_dict_round_trip():
    dt = datetime(2026, 4, 18, 9, 0, tzinfo=timezone.utc)
    c = Comment(id="c1", platform="reddit", author="Alice", date=dt,
                text="hi", likes=1, position=0)
    post = Post(
        id="p1", platform="reddit", url="https://reddit.com/r/test/x",
        page_title="r/test", post_title="Test", date=dt, author="op",
        content="body", likes=10, comments=[c],
    )
    d = post.to_dict()
    assert d["id"] == "p1"
    assert d["comments"][0]["id"] == "c1"

    restored = Post.from_dict(d)
    assert restored == post


def test_scrape_error_still_works():
    err = ScrapeError("boom", cause="timeout")
    assert err.cause == "timeout"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_scraping/test_models.py -v
```

Expected: FAIL — new fields and `to_dict`/`from_dict` don't exist yet.

- [ ] **Step 3: Rewrite `autoso/scraping/models.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any


class ScrapeError(Exception):
    """Base exception for scraping failures with classified cause.

    cause values: "auth_wall" | "proxy" | "selector_drift" | "rate_limit" | "timeout" | "unknown"
    """
    def __init__(self, message: str, cause: str = "unknown"):
        super().__init__(message)
        self.cause = cause


@dataclass
class Comment:
    id: str
    platform: str
    author: str | None
    date: datetime | None
    text: str
    likes: int | None
    position: int
    subcomments: list["Comment"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "platform": self.platform,
            "author": self.author,
            "date": self.date.isoformat() if self.date else None,
            "text": self.text,
            "likes": self.likes,
            "position": self.position,
            "subcomments": [sc.to_dict() for sc in self.subcomments],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Comment":
        return cls(
            id=d["id"],
            platform=d["platform"],
            author=d.get("author"),
            date=datetime.fromisoformat(d["date"]) if d.get("date") else None,
            text=d["text"],
            likes=d.get("likes"),
            position=d["position"],
            subcomments=[cls.from_dict(sc) for sc in d.get("subcomments", [])],
        )


@dataclass
class Post:
    id: str
    platform: str
    url: str
    page_title: str
    post_title: str
    date: datetime | None
    author: str | None
    content: str | None
    likes: int | None
    comments: list[Comment] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "platform": self.platform,
            "url": self.url,
            "page_title": self.page_title,
            "post_title": self.post_title,
            "date": self.date.isoformat() if self.date else None,
            "author": self.author,
            "content": self.content,
            "likes": self.likes,
            "comments": [c.to_dict() for c in self.comments],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Post":
        return cls(
            id=d["id"],
            platform=d["platform"],
            url=d["url"],
            page_title=d["page_title"],
            post_title=d["post_title"],
            date=datetime.fromisoformat(d["date"]) if d.get("date") else None,
            author=d.get("author"),
            content=d.get("content"),
            likes=d.get("likes"),
            comments=[Comment.from_dict(c) for c in d.get("comments", [])],
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_scraping/test_models.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add autoso/scraping/models.py tests/test_scraping/test_models.py
git commit -m "feat(scraping): new Post/Comment model with nested replies and JSON round-trip"
```

---

## Task 2: Supabase Migration SQL

**Files:**
- Create: `migrations/003_scrapes_table.sql`

- [ ] **Step 1: Create the migration file**

```sql
-- AutoSO Phase 1X: scrapes cache table + analyses.scrape_id reference.
-- Run in Supabase dashboard: SQL Editor after 001_initial_schema.sql and 002_transcripts_table.sql.
-- This truncates all prior analyses/citations rows (Phase 1X has no backward compat).

TRUNCATE TABLE citations, analyses RESTART IDENTITY CASCADE;

CREATE TABLE IF NOT EXISTS scrapes (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    url        TEXT        NOT NULL,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    result     JSONB       NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scrapes_url_scraped_at
    ON scrapes (url, scraped_at DESC);

ALTER TABLE analyses
    ADD COLUMN IF NOT EXISTS scrape_id UUID REFERENCES scrapes(id);
```

- [ ] **Step 2: Commit**

```bash
git add migrations/003_scrapes_table.sql
git commit -m "feat(migrations): add scrapes table and analyses.scrape_id"
```

---

## Task 3: Supabase Storage Functions

**Files:**
- Modify: `autoso/storage/supabase.py`
- Modify: `tests/test_storage/test_supabase.py`

- [ ] **Step 1: Read existing storage test file for style**

```bash
cat tests/test_storage/test_supabase.py
```

- [ ] **Step 2: Write failing tests in `tests/test_storage/test_supabase.py`**

Add these tests to the existing file (keep any tests already present that still apply to the new `store_result` signature):

```python
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from autoso.scraping.models import Post, Comment
from autoso.storage.supabase import (
    store_result, store_scrape, get_recent_scrape,
)


def _sample_post() -> Post:
    dt = datetime(2026, 4, 18, 9, 0, tzinfo=timezone.utc)
    return Post(
        id="p1", platform="reddit", url="https://reddit.com/r/t/x",
        page_title="r/t", post_title="Title", date=dt, author="op",
        content="body", likes=5,
        comments=[Comment(id="c1", platform="reddit", author="a", date=dt,
                          text="hi", likes=1, position=0)],
    )


@patch("autoso.storage.supabase._get_client")
def test_store_scrape_inserts_and_returns_id(mock_client):
    fake = MagicMock()
    mock_client.return_value = fake
    fake.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": "uuid-1"}
    ]

    post = _sample_post()
    scrape_id = store_scrape("https://reddit.com/r/t/x", post)

    assert scrape_id == "uuid-1"
    args = fake.table.return_value.insert.call_args.args[0]
    assert args["url"] == "https://reddit.com/r/t/x"
    assert args["result"]["id"] == "p1"
    assert args["result"]["comments"][0]["id"] == "c1"


@patch("autoso.storage.supabase._get_client")
def test_get_recent_scrape_returns_post_when_fresh(mock_client):
    fake = MagicMock()
    mock_client.return_value = fake
    post = _sample_post()
    recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    fake.table.return_value.select.return_value.eq.return_value.gte.return_value \
        .order.return_value.limit.return_value.execute.return_value.data = [
        {"id": "uuid-1", "scraped_at": recent, "result": post.to_dict()}
    ]

    result = get_recent_scrape("https://reddit.com/r/t/x")
    assert result is not None
    sid, p = result
    assert sid == "uuid-1"
    assert p.id == "p1"
    assert p.comments[0].id == "c1"


@patch("autoso.storage.supabase._get_client")
def test_get_recent_scrape_returns_none_when_no_rows(mock_client):
    fake = MagicMock()
    mock_client.return_value = fake
    fake.table.return_value.select.return_value.eq.return_value.gte.return_value \
        .order.return_value.limit.return_value.execute.return_value.data = []

    assert get_recent_scrape("https://reddit.com/r/t/x") is None


@patch("autoso.storage.supabase._get_client")
def test_store_result_requires_scrape_id(mock_client):
    fake = MagicMock()
    mock_client.return_value = fake

    run_id = store_result(
        url="u", mode="texture", title="t", output="o",
        output_cited="oc", citation_index=[], scrape_id="uuid-1",
    )
    row = fake.table.return_value.insert.call_args_list[0].args[0]
    assert row["scrape_id"] == "uuid-1"
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_storage/test_supabase.py -v
```

Expected: FAIL — `store_scrape`, `get_recent_scrape` don't exist; `store_result` doesn't accept `scrape_id`.

- [ ] **Step 4: Update `autoso/storage/supabase.py`**

```python
# autoso/storage/supabase.py
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from supabase import create_client, Client

import autoso.config as config
from autoso.scraping.models import Post


CACHE_WINDOW_MINUTES = 30


def _get_client() -> Client:
    return create_client(config.SUPABASE_URL, config.SUPABASE_KEY)


def store_scrape(url: str, post: Post) -> str:
    """Persist a Post as a scrape cache row. Returns the scrape_id (UUID)."""
    client = _get_client()
    scrape_id = str(uuid.uuid4())
    client.table("scrapes").insert({
        "id": scrape_id,
        "url": url,
        "result": post.to_dict(),
    }).execute()
    return scrape_id


def get_recent_scrape(url: str) -> tuple[str, Post] | None:
    """Return the most recent scrape for `url` within the cache window, or None."""
    client = _get_client()
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=CACHE_WINDOW_MINUTES)).isoformat()
    resp = (
        client.table("scrapes")
        .select("id, scraped_at, result")
        .eq("url", url)
        .gte("scraped_at", cutoff)
        .order("scraped_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    if not rows:
        return None
    row = rows[0]
    return row["id"], Post.from_dict(row["result"])


def store_result(
    url: str,
    mode: str,
    title: str,
    output: str,
    output_cited: Optional[str],
    citation_index: List[dict],
    scrape_id: str,
) -> str:
    """Persist an analysis result and its citations. Returns the run_id (UUID)."""
    client = _get_client()
    run_id = str(uuid.uuid4())

    client.table("analyses").insert({
        "id": run_id,
        "url": url,
        "mode": mode,
        "title": title,
        "output": output,
        "output_cited": output_cited,
        "scrape_id": scrape_id,
    }).execute()

    if citation_index:
        rows = [
            {
                "run_id": run_id,
                "citation_number": c["citation_number"],
                "text": c["text"],
                "platform": c["platform"],
                "comment_id": c.get("comment_id"),
                "position": c.get("position"),
            }
            for c in citation_index
        ]
        client.table("citations").insert(rows).execute()

    return run_id
```

- [ ] **Step 5: Run storage tests to verify they pass**

```bash
pytest tests/test_storage/test_supabase.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add autoso/storage/supabase.py tests/test_storage/test_supabase.py
git commit -m "feat(storage): add scrape cache helpers and require scrape_id on store_result"
```

---

# Step 2: Pipeline Compatibility for New Model

## Task 4: Update CitationNode and Indexer for Renamed `id` Field

**Files:**
- Modify: `autoso/pipeline/citation.py`
- Modify: `autoso/pipeline/indexer.py`
- Modify: `tests/test_pipeline/test_citation.py`
- Modify: `tests/test_pipeline/test_indexer.py`

- [ ] **Step 1: Read existing citation + indexer tests**

```bash
cat tests/test_pipeline/test_citation.py tests/test_pipeline/test_indexer.py
```

- [ ] **Step 2: Update `autoso/pipeline/citation.py`**

Change the `CitationNode` field name from `comment_id` to `id`, and update the metadata read:

```python
# autoso/pipeline/citation.py
import re
from dataclasses import dataclass
from typing import List

from llama_index.core import VectorStoreIndex
from llama_index.core.query_engine import CitationQueryEngine


@dataclass
class CitationNode:
    citation_number: int
    text: str
    platform: str
    id: str
    position: int


def build_citation_engine(
    index: VectorStoreIndex,
    similarity_top_k: int = 10,
    system_prompt: str | None = None,
) -> CitationQueryEngine:
    """Build a CitationQueryEngine that annotates its response with [N] markers."""
    kwargs: dict = {
        "similarity_top_k": similarity_top_k,
        "citation_chunk_size": 512,
    }
    if system_prompt:
        from llama_index.core import PromptTemplate
        qa_template = PromptTemplate(
            "INSTRUCTIONS:\n" + system_prompt + "\n\n"
            "Context information is below.\n"
            "---------------------\n"
            "{context_str}\n"
            "---------------------\n"
            "Given the context information and not prior knowledge, "
            "answer the query.\n"
            "Query: {query_str}\n"
            "Answer: "
        )
        kwargs["text_qa_template"] = qa_template
    return CitationQueryEngine.from_args(index, **kwargs)


def extract_citations(response) -> List[CitationNode]:
    """Extract source node metadata from a CitationQueryEngine response."""
    nodes = []
    for i, node in enumerate(response.source_nodes):
        nodes.append(
            CitationNode(
                citation_number=i + 1,
                text=node.node.text,
                platform=node.node.metadata.get("platform", "unknown"),
                id=node.node.metadata.get("id", f"node_{i}"),
                position=node.node.metadata.get("position", -1),
            )
        )
    return nodes


def strip_citation_markers(text: str) -> str:
    """Remove all [N] citation markers from text."""
    return re.sub(r"\s*\[\d+\]", "", text).strip()
```

- [ ] **Step 3: Update `autoso/pipeline/indexer.py`**

Change metadata and `doc_id` to use `comment.id`:

```python
# autoso/pipeline/indexer.py
import uuid
from typing import List

import chromadb
from llama_index.core import Document, VectorStoreIndex, StorageContext
from llama_index.vector_stores.chroma import ChromaVectorStore

from autoso.scraping.models import Comment


def index_comments(
    comments: List[Comment], collection_name: str | None = None
) -> VectorStoreIndex:
    """Index comments into an ephemeral (in-memory) ChromaDB collection."""
    if collection_name is None:
        collection_name = f"run_{uuid.uuid4().hex[:12]}"

    client = chromadb.EphemeralClient()
    collection = client.create_collection(collection_name)
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    documents = [
        Document(
            text=comment.text,
            metadata={
                "platform": comment.platform,
                "id": comment.id,
                "position": comment.position,
            },
            doc_id=comment.id,
        )
        for comment in comments
    ]

    return VectorStoreIndex.from_documents(
        documents, storage_context=storage_context, show_progress=False
    )
```

- [ ] **Step 4: Update `tests/test_pipeline/test_citation.py` and `tests/test_pipeline/test_indexer.py`**

In both test files, replace every occurrence of `comment_id` with `id` (both in metadata dicts handed to mocks and in assertions about `CitationNode`). Replace every `Comment(...comment_id=..., ...)` constructor call with the new field signature: `Comment(id=..., platform=..., author=None, date=None, text=..., likes=None, position=...)`.

For example, in `test_indexer.py`, an existing call like:
```python
Comment(platform="reddit", text="hi", comment_id="c1", position=0)
```
becomes:
```python
Comment(id="c1", platform="reddit", author=None, date=None, text="hi", likes=None, position=0)
```

And an assertion like:
```python
assert nodes[0].comment_id == "c1"
```
becomes:
```python
assert nodes[0].id == "c1"
```

- [ ] **Step 5: Run pipeline tests to verify they pass**

```bash
pytest tests/test_pipeline/test_citation.py tests/test_pipeline/test_indexer.py -v
```

Expected: PASS.

- [ ] **Step 6: Update citation_index dict in `autoso/pipeline/pipeline.py`**

The pipeline builds a `citation_index` dict passed to `store_result`. The dict uses key `comment_id` for the Supabase `citations` table column (that column name stays the same). But the source field on `CitationNode` is now `.id`, so update the read:

In `autoso/pipeline/pipeline.py`, find:
```python
citation_index=[
    {
        "citation_number": c.citation_number,
        "text": c.text,
        "platform": c.platform,
        "comment_id": c.comment_id,
        "position": c.position,
    }
    for c in citations
],
```
Replace with:
```python
citation_index=[
    {
        "citation_number": c.citation_number,
        "text": c.text,
        "platform": c.platform,
        "comment_id": c.id,
        "position": c.position,
    }
    for c in citations
],
```

- [ ] **Step 7: Commit**

```bash
git add autoso/pipeline/citation.py autoso/pipeline/indexer.py autoso/pipeline/pipeline.py tests/test_pipeline/test_citation.py tests/test_pipeline/test_indexer.py
git commit -m "refactor(pipeline): rename Comment.comment_id to Comment.id"
```

---

# Step 3: Reddit Rewrite & Existing Scraper Updates

## Task 5: Reddit JSON API Rewrite

**Files:**
- Rewrite: `autoso/scraping/reddit.py`
- Rewrite: `tests/test_scraping/test_reddit.py`

- [ ] **Step 1: Rewrite `tests/test_scraping/test_reddit.py`**

```python
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from autoso.scraping.reddit import RedditScraper
from autoso.scraping.models import Post


def _reddit_json(post_data: dict, comments: list[dict]) -> list:
    """Build a mock Reddit JSON response: [post_listing, comment_listing]."""
    post_listing = {"data": {"children": [{"kind": "t3", "data": post_data}]}}
    comment_listing = {
        "data": {"children": [{"kind": "t1", "data": c} for c in comments]}
    }
    return [post_listing, comment_listing]


def _mock_response(json_payload):
    resp = MagicMock()
    resp.json.return_value = json_payload
    resp.raise_for_status = MagicMock()
    return resp


@patch("autoso.scraping.reddit.httpx.get")
def test_scrape_builds_post_from_json(mock_get):
    post_data = {
        "id": "abc123",
        "title": "Test Post",
        "selftext": "Post body",
        "author": "op_user",
        "score": 42,
        "created_utc": 1713436800,  # 2024-04-18T08:00:00Z
        "subreddit_name_prefixed": "r/singapore",
    }
    comments = [
        {
            "id": "c1", "body": "First comment", "author": "user1",
            "score": 5, "created_utc": 1713436900, "replies": "",
        },
        {
            "id": "c2", "body": "Second comment", "author": "user2",
            "score": 3, "created_utc": 1713437000,
            "replies": {"data": {"children": [
                {"kind": "t1", "data": {
                    "id": "r1", "body": "Reply", "author": "user3",
                    "score": 1, "created_utc": 1713437050, "replies": "",
                }},
            ]}},
        },
    ]
    mock_get.return_value = _mock_response(_reddit_json(post_data, comments))

    scraper = RedditScraper()
    post = scraper.scrape("https://www.reddit.com/r/singapore/comments/abc123/test/")

    assert isinstance(post, Post)
    assert post.platform == "reddit"
    assert post.id == "abc123"
    assert post.post_title == "Test Post"
    assert post.content == "Post body"
    assert post.author == "op_user"
    assert post.likes == 42
    assert post.page_title == "r/singapore"
    assert post.date is not None
    assert len(post.comments) == 2
    assert post.comments[0].id == "c1"
    assert post.comments[0].author == "user1"
    assert post.comments[0].text == "First comment"
    assert post.comments[0].likes == 5
    assert post.comments[0].position == 0
    assert post.comments[0].subcomments == []
    assert len(post.comments[1].subcomments) == 1
    assert post.comments[1].subcomments[0].id == "r1"
    assert post.comments[1].subcomments[0].text == "Reply"


@patch("autoso.scraping.reddit.httpx.get")
def test_scrape_filters_deleted_and_removed(mock_get):
    comments = [
        {"id": "d1", "body": "[deleted]", "author": "[deleted]",
         "score": 0, "created_utc": 1713436900, "replies": ""},
        {"id": "d2", "body": "[removed]", "author": "mod",
         "score": 0, "created_utc": 1713437000, "replies": ""},
        {"id": "c1", "body": "Normal", "author": "u",
         "score": 1, "created_utc": 1713437100, "replies": ""},
    ]
    post_data = {"id": "x", "title": "T", "selftext": "",
                 "author": "op", "score": 1, "created_utc": 1,
                 "subreddit_name_prefixed": "r/t"}
    mock_get.return_value = _mock_response(_reddit_json(post_data, comments))

    scraper = RedditScraper()
    post = scraper.scrape("https://www.reddit.com/r/t/comments/x/y/")

    assert len(post.comments) == 1
    assert post.comments[0].text == "Normal"


@patch("autoso.scraping.reddit.httpx.get")
def test_scrape_skips_more_kind_nodes(mock_get):
    post_data = {"id": "x", "title": "T", "selftext": "",
                 "author": "op", "score": 1, "created_utc": 1,
                 "subreddit_name_prefixed": "r/t"}
    payload = [
        {"data": {"children": [{"kind": "t3", "data": post_data}]}},
        {"data": {"children": [
            {"kind": "t1", "data": {"id": "c1", "body": "hi", "author": "u",
                                    "score": 1, "created_utc": 2, "replies": ""}},
            {"kind": "more", "data": {"count": 100}},
        ]}},
    ]
    mock_get.return_value = _mock_response(payload)

    scraper = RedditScraper()
    post = scraper.scrape("https://www.reddit.com/r/t/comments/x/y/")

    assert len(post.comments) == 1


@patch("autoso.scraping.reddit.httpx.get")
def test_scrape_appends_json_suffix(mock_get):
    post_data = {"id": "x", "title": "T", "selftext": "",
                 "author": "op", "score": 1, "created_utc": 1,
                 "subreddit_name_prefixed": "r/t"}
    mock_get.return_value = _mock_response(_reddit_json(post_data, []))

    scraper = RedditScraper()
    scraper.scrape("https://www.reddit.com/r/t/comments/x/y/")

    called_url = mock_get.call_args.args[0]
    assert called_url.endswith(".json")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_scraping/test_reddit.py -v
```

Expected: FAIL — new scraper doesn't exist yet / old one uses PRAW.

- [ ] **Step 3: Rewrite `autoso/scraping/reddit.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from autoso.scraping.models import Comment, Post, ScrapeError


_USER_AGENT = "AutoSO/1.0 (scraping)"
_TIMEOUT = 20.0


class RedditScraper:
    def scrape(self, url: str) -> Post:
        json_url = url.rstrip("/") + ".json"
        try:
            resp = httpx.get(
                json_url,
                headers={"User-Agent": _USER_AGENT},
                follow_redirects=True,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            payload = resp.json()
        except httpx.TimeoutException as exc:
            raise ScrapeError(f"Reddit JSON fetch timed out: {exc}", cause="timeout")
        except httpx.HTTPStatusError as exc:
            cause = "rate_limit" if exc.response.status_code == 429 else "unknown"
            raise ScrapeError(f"Reddit JSON HTTP error: {exc}", cause=cause)
        except Exception as exc:
            raise ScrapeError(f"Reddit JSON fetch failed: {exc}", cause="unknown")

        if not isinstance(payload, list) or len(payload) < 2:
            raise ScrapeError("Unexpected Reddit JSON shape", cause="selector_drift")

        post_listing, comment_listing = payload[0], payload[1]
        post_children = post_listing.get("data", {}).get("children", [])
        if not post_children:
            raise ScrapeError("Reddit post listing empty", cause="selector_drift")

        post_data = post_children[0].get("data", {})
        comment_children = comment_listing.get("data", {}).get("children", [])

        comments = _build_comments(comment_children)

        return Post(
            id=post_data.get("id", ""),
            platform="reddit",
            url=url,
            page_title=post_data.get("subreddit_name_prefixed", "") or "reddit",
            post_title=post_data.get("title", ""),
            date=_epoch_to_datetime(post_data.get("created_utc")),
            author=post_data.get("author"),
            content=post_data.get("selftext") or post_data.get("title", ""),
            likes=post_data.get("score"),
            comments=comments,
        )


def _epoch_to_datetime(epoch: float | None) -> datetime | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc)


def _is_deleted(body: str | None, author: str | None) -> bool:
    if body is None:
        return True
    stripped = body.strip()
    return stripped in ("[deleted]", "[removed]")


def _build_comments(children: list[dict[str, Any]]) -> list[Comment]:
    """Convert Reddit comment children into top-level Comments with nested subcomments."""
    comments: list[Comment] = []
    position = 0
    for child in children:
        if child.get("kind") != "t1":
            continue  # skip "more" and other kinds
        data = child.get("data", {})
        if _is_deleted(data.get("body"), data.get("author")):
            continue
        comment = _child_to_comment(data, position)
        comments.append(comment)
        position += 1
    return comments


def _child_to_comment(data: dict[str, Any], position: int) -> Comment:
    subcomments: list[Comment] = []
    replies = data.get("replies")
    if isinstance(replies, dict):
        reply_children = replies.get("data", {}).get("children", [])
        sub_position = 0
        for rc in reply_children:
            if rc.get("kind") != "t1":
                continue
            rdata = rc.get("data", {})
            if _is_deleted(rdata.get("body"), rdata.get("author")):
                continue
            subcomments.append(_child_to_comment(rdata, sub_position))
            sub_position += 1

    return Comment(
        id=data.get("id", ""),
        platform="reddit",
        author=data.get("author"),
        date=_epoch_to_datetime(data.get("created_utc")),
        text=data.get("body", ""),
        likes=data.get("score"),
        position=position,
        subcomments=subcomments,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_scraping/test_reddit.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add autoso/scraping/reddit.py tests/test_scraping/test_reddit.py
git commit -m "feat(reddit): rewrite scraper using Reddit JSON API instead of PRAW"
```

---

## Task 6: Remove PRAW and Reddit API Credentials

**Files:**
- Modify: `autoso/config.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Edit `autoso/config.py`**

Delete these three lines:
```python
REDDIT_CLIENT_ID: str = os.environ["REDDIT_CLIENT_ID"]
REDDIT_CLIENT_SECRET: str = os.environ["REDDIT_CLIENT_SECRET"]
REDDIT_USER_AGENT: str = os.environ.get("REDDIT_USER_AGENT", "AutoSO/1.0")
```

- [ ] **Step 2: Edit `pyproject.toml`**

Remove the line `"praw>=7.7.0",` from `dependencies`. Add `"httpx>=0.27.0",` to `dependencies` if not already there (it currently sits under `dev` optional-deps; move it to main).

- [ ] **Step 3: Re-install to sync dependency removal**

```bash
pip install -e '.[dev]'
```

Expected: `praw` uninstalled (if present), `httpx` usable at runtime.

- [ ] **Step 4: Verify Reddit tests still pass and no other code imports praw**

```bash
grep -rn "praw" autoso/ tests/ --include="*.py"
pytest tests/test_scraping/test_reddit.py -v
```

Expected: no remaining references; tests pass.

- [ ] **Step 5: Commit**

```bash
git add autoso/config.py pyproject.toml
git commit -m "chore: drop PRAW dependency and Reddit API credential env vars"
```

---

## Task 7: Facebook Scraper — Populate New Fields & Nest Replies

**Files:**
- Modify: `autoso/scraping/facebook.py`
- Modify: `tests/test_scraping/test_facebook.py`

- [ ] **Step 1: Rewrite `tests/test_scraping/test_facebook.py`**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from autoso.scraping.facebook import FacebookScraper
from autoso.scraping.models import Post


def _empty_locator() -> AsyncMock:
    """AsyncMock locator that behaves as an empty / invisible element."""
    loc = AsyncMock()
    loc.count = AsyncMock(return_value=0)
    loc.inner_text = AsyncMock(return_value="")
    loc.get_attribute = AsyncMock(return_value=None)
    loc.is_visible = AsyncMock(return_value=False)
    loc.bounding_box = AsyncMock(return_value=None)
    loc.evaluate = AsyncMock(return_value=False)
    loc.first = loc
    loc.last = loc
    loc.nth = MagicMock(return_value=loc)
    return loc


@pytest.mark.asyncio
@patch("autoso.scraping.facebook.async_playwright")
@patch("autoso.scraping.facebook.stealth_async", new_callable=AsyncMock)
async def test_scrape_returns_post_with_new_fields(mock_stealth, mock_pw):
    scraper = FacebookScraper()

    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = MagicMock()
    mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_pw.return_value)
    mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_pw.return_value.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.storage_state = AsyncMock(return_value={})

    mock_page.goto = AsyncMock(return_value=None)
    mock_page.url = "https://www.facebook.com/mindef/posts/123"
    mock_page.content = AsyncMock(return_value="<html></html>")
    mock_page.evaluate = AsyncMock(return_value=None)
    mock_page.mouse.move = AsyncMock()
    mock_page.mouse.wheel = AsyncMock()

    empty = _empty_locator()
    mock_page.locator = MagicMock(return_value=empty)
    mock_page.get_by_text = MagicMock(return_value=empty)

    post = await scraper._scrape_async("https://www.facebook.com/mindef/posts/123")

    assert isinstance(post, Post)
    assert post.platform == "facebook"
    assert post.url == "https://www.facebook.com/mindef/posts/123"
    # New fields must be present with safe defaults when unextractable:
    assert post.id.startswith("fb_")
    assert post.page_title is not None
    assert post.post_title is not None
    assert post.likes is None or isinstance(post.likes, int)
    assert post.comments == []
```

(Note: this test only covers the "no comments loaded" path. The FB extraction code is heavily DOM-dependent and hard to exercise in unit tests without an excessive mock scaffold; a live integration test in `tests/integration/` already exercises it.)

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_scraping/test_facebook.py -v
```

Expected: FAIL — new fields on `Post` not populated.

- [ ] **Step 3: Update `autoso/scraping/facebook.py`**

Replace the `_scrape_async` return statement to populate the new `Post` fields, and update `_extract_comments` to populate new `Comment` fields and nest replies as `subcomments`.

Replace the entire class body's `_scrape_async`, `_extract_comments`, and add helper methods. The updated file:

```python
import asyncio
import re
from datetime import datetime, timezone
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
        # (unchanged from previous implementation — keep existing body)
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
                    await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
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
        """Extract top-level comments.

        Facebook nests reply articles inside their parent's `[aria-label^='Comment by']`
        element. We walk only top-level articles (no ancestor with that aria-label)
        and attach nested reply articles as `subcomments`.
        """
        articles = page.locator("[aria-label^='Comment by']")
        count = await articles.count()
        top_level: List[Comment] = []
        position = 0

        for i in range(count):
            article = articles.nth(i)
            # Skip if this article has an ancestor matching the same selector (it's a reply)
            is_reply = await article.evaluate(
                "el => !!el.parentElement && !!el.parentElement.closest('[aria-label^=\"Comment by\"]')"
            )
            if is_reply:
                continue

            parent_comment = await self._build_comment(article, position, is_subcomment=False)
            if parent_comment is None:
                continue

            # Find nested replies within this article
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

    async def _build_comment(self, article, position: int, is_subcomment: bool) -> Comment | None:
        try:
            # author from aria-label "Comment by <name>"
            label = (await article.get_attribute("aria-label")) or ""
            author_match = re.match(r"Comment by (.+)", label)
            author = author_match.group(1).strip() if author_match else None

            # text from second span[dir='auto']
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

            # date
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

            # likes
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
    # Extract final path segment with digits, fallback to hash
    m = re.search(r"/(\d{5,})", url)
    if m:
        return f"fb_{m.group(1)}"
    return f"fb_{abs(hash(url)) % 10_000_000_000}"
```

- [ ] **Step 4: Run Facebook tests to verify they pass**

```bash
pytest tests/test_scraping/test_facebook.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add autoso/scraping/facebook.py tests/test_scraping/test_facebook.py
git commit -m "feat(facebook): populate new Post/Comment fields and nest replies"
```

---

## Task 8: Instagram Scraper — Populate New Fields

**Files:**
- Modify: `autoso/scraping/instagram.py`
- Modify: `tests/test_scraping/test_instagram.py`

- [ ] **Step 1: Update `tests/test_scraping/test_instagram.py`**

Edit the first test `test_scrape_returns_post_with_correct_platform` to add these assertions after the existing ones:

```python
    assert post.id == "ig_ABC123"
    assert post.page_title is not None
    assert post.post_title is not None
    # Optional fields default to None when selectors don't match
    assert post.date is None
    assert post.author is None
    assert post.likes is None
```

Edit the second test `test_scrape_extracts_comments` to verify new `Comment` fields on every extracted comment:

```python
    for c in post.comments:
        assert c.id.startswith("ig_")
        assert c.platform == "instagram"
        assert c.author is None
        assert c.date is None
        assert c.likes is None
        assert isinstance(c.position, int)
        assert c.subcomments == []
```

Remove any lingering references to `comment_id=` kwargs in `Comment(...)` constructors if present (there shouldn't be any in this file currently).

- [ ] **Step 2: Run test to verify failures**

```bash
pytest tests/test_scraping/test_instagram.py -v
```

Expected: FAIL.

- [ ] **Step 3: Update `autoso/scraping/instagram.py`**

Replace the contents with:

```python
import asyncio
import re
from datetime import datetime
from typing import List
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from autoso.scraping.playwright_base import PlaywrightScraper
from autoso.scraping.models import Comment, Post, ScrapeError


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
        """Instagram comment DOM is notoriously flat and unlabeled — we cannot
        reliably distinguish top-level from reply, so subcomments always empty."""
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
```

- [ ] **Step 4: Run Instagram tests to verify they pass**

```bash
pytest tests/test_scraping/test_instagram.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add autoso/scraping/instagram.py tests/test_scraping/test_instagram.py
git commit -m "feat(instagram): populate new Post/Comment fields"
```

---

# Step 4: Dispatch, Cache, and Pipeline Integration

## Task 9: Extend Platform Detection for New Platforms

**Files:**
- Modify: `autoso/scraping/base.py`
- Modify: `tests/test_scraping/test_factory.py`

- [ ] **Step 1: Rewrite `tests/test_scraping/test_factory.py`**

```python
import pytest
from autoso.scraping.base import detect_platform, get_scraper


def test_detect_platform_reddit():
    assert detect_platform("https://www.reddit.com/r/singapore/comments/abc") == "reddit"


def test_detect_platform_instagram():
    assert detect_platform("https://www.instagram.com/p/ABC123/") == "instagram"


def test_detect_platform_facebook():
    assert detect_platform("https://www.facebook.com/mindef/posts/123") == "facebook"


def test_detect_platform_hardwarezone():
    assert detect_platform("https://forums.hardwarezone.com.sg/threads/foo.1234/") == "hardwarezone"


def test_detect_platform_youtube_long():
    assert detect_platform("https://www.youtube.com/watch?v=abc") == "youtube"


def test_detect_platform_youtube_short():
    assert detect_platform("https://youtu.be/abc") == "youtube"


def test_detect_platform_tiktok():
    assert detect_platform("https://www.tiktok.com/@user/video/123") == "tiktok"


def test_detect_platform_unsupported_raises():
    with pytest.raises(ValueError, match="Unsupported platform"):
        detect_platform("https://twitter.com/x/status/1")


def test_get_scraper_returns_correct_type():
    from autoso.scraping.reddit import RedditScraper
    from autoso.scraping.instagram import InstagramScraper
    from autoso.scraping.facebook import FacebookScraper
    from autoso.scraping.hardwarezone import HardwareZoneScraper
    from autoso.scraping.youtube import YouTubeScraper
    from autoso.scraping.tiktok import TikTokScraper

    assert isinstance(get_scraper("https://reddit.com/r/x/comments/y"), RedditScraper)
    assert isinstance(get_scraper("https://instagram.com/p/ABC/"), InstagramScraper)
    assert isinstance(get_scraper("https://facebook.com/m/posts/1"), FacebookScraper)
    assert isinstance(get_scraper("https://forums.hardwarezone.com.sg/threads/a.1/"), HardwareZoneScraper)
    assert isinstance(get_scraper("https://youtube.com/watch?v=a"), YouTubeScraper)
    assert isinstance(get_scraper("https://tiktok.com/@u/video/1"), TikTokScraper)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_scraping/test_factory.py::test_detect_platform_hardwarezone -v
```

Expected: FAIL — new platforms not in detector; new scraper modules don't exist yet.

- [ ] **Step 3: Update `autoso/scraping/base.py`**

```python
from urllib.parse import urlparse


def detect_platform(url: str) -> str:
    """Detect the social platform from a URL. Hostname-based matching."""
    hostname = urlparse(url).hostname or ""
    bare = hostname.removeprefix("www.").removeprefix("m.")

    if bare == "reddit.com" or bare.endswith(".reddit.com"):
        return "reddit"
    if bare == "instagram.com" or bare.endswith(".instagram.com"):
        return "instagram"
    if bare == "facebook.com" or bare.endswith(".facebook.com") or bare == "fb.com":
        return "facebook"
    if bare == "hardwarezone.com.sg" or bare.endswith(".hardwarezone.com.sg"):
        return "hardwarezone"
    if bare == "youtube.com" or bare.endswith(".youtube.com") or bare == "youtu.be":
        return "youtube"
    if bare == "tiktok.com" or bare.endswith(".tiktok.com"):
        return "tiktok"
    raise ValueError(f"Unsupported platform for URL: {url}")


def get_scraper(url: str):
    """Return the appropriate scraper instance for the given URL."""
    platform = detect_platform(url)
    if platform == "reddit":
        from autoso.scraping.reddit import RedditScraper
        return RedditScraper()
    if platform == "instagram":
        from autoso.scraping.instagram import InstagramScraper
        return InstagramScraper()
    if platform == "facebook":
        from autoso.scraping.facebook import FacebookScraper
        return FacebookScraper()
    if platform == "hardwarezone":
        from autoso.scraping.hardwarezone import HardwareZoneScraper
        return HardwareZoneScraper()
    if platform == "youtube":
        from autoso.scraping.youtube import YouTubeScraper
        return YouTubeScraper()
    if platform == "tiktok":
        from autoso.scraping.tiktok import TikTokScraper
        return TikTokScraper()
    raise ValueError(f"No scraper registered for platform: {platform}")
```

(Note: the `detect_platform_*` tests pass now; `get_scraper` tests for new platforms still fail until their modules exist — that's expected. The `test_get_scraper_returns_correct_type` test will be re-run at the end of the plan.)

- [ ] **Step 4: Run detection-only tests to verify they pass**

```bash
pytest tests/test_scraping/test_factory.py -v -k "detect_platform"
```

Expected: All `test_detect_platform_*` PASS.

- [ ] **Step 5: Commit**

```bash
git add autoso/scraping/base.py tests/test_scraping/test_factory.py
git commit -m "feat(scraping): extend platform detection for HardwareZone, YouTube, TikTok"
```

---

## Task 10: Unified scrape() with Cache + flatten_comments Helper

**Files:**
- Rewrite: `autoso/scraping/__init__.py`
- Create: `tests/test_scraping/test_dispatch.py`

- [ ] **Step 1: Create `tests/test_scraping/test_dispatch.py`**

```python
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from autoso.scraping import scrape, flatten_comments
from autoso.scraping.models import Post, Comment


def _sample_post() -> Post:
    dt = datetime(2026, 4, 18, 9, 0, tzinfo=timezone.utc)
    reply = Comment(id="r1", platform="reddit", author="b", date=dt,
                    text="reply", likes=1, position=0)
    parent = Comment(id="c1", platform="reddit", author="a", date=dt,
                     text="parent", likes=2, position=0, subcomments=[reply])
    top = Comment(id="c2", platform="reddit", author="c", date=dt,
                  text="top2", likes=3, position=1)
    return Post(
        id="p1", platform="reddit", url="https://reddit.com/r/t/x",
        page_title="r/t", post_title="T", date=dt, author="op",
        content="body", likes=5, comments=[parent, top],
    )


@patch("autoso.scraping.get_recent_scrape")
@patch("autoso.scraping.get_scraper")
@patch("autoso.scraping.store_scrape")
def test_scrape_returns_cached_post_on_hit(mock_store, mock_factory, mock_get_recent):
    post = _sample_post()
    mock_get_recent.return_value = ("cached-sid", post)

    scrape_id, result = scrape("https://reddit.com/r/t/x")

    assert scrape_id == "cached-sid"
    assert result is post
    mock_factory.assert_not_called()
    mock_store.assert_not_called()


@patch("autoso.scraping.get_recent_scrape")
@patch("autoso.scraping.get_scraper")
@patch("autoso.scraping.store_scrape")
def test_scrape_invokes_scraper_and_stores_on_miss(mock_store, mock_factory, mock_get_recent):
    post = _sample_post()
    mock_get_recent.return_value = None
    mock_scraper = MagicMock()
    mock_scraper.scrape.return_value = post
    mock_factory.return_value = mock_scraper
    mock_store.return_value = "new-sid"

    scrape_id, result = scrape("https://reddit.com/r/t/x")

    assert scrape_id == "new-sid"
    assert result is post
    mock_scraper.scrape.assert_called_once_with("https://reddit.com/r/t/x")
    mock_store.assert_called_once_with("https://reddit.com/r/t/x", post)


def test_flatten_comments_returns_all_comments_depth_first():
    post = _sample_post()
    flat = flatten_comments(post)
    assert len(flat) == 3
    assert flat[0].id == "c1"
    assert flat[1].id == "r1"
    assert flat[2].id == "c2"


def test_flatten_comments_empty_when_no_comments():
    dt = datetime(2026, 4, 18, tzinfo=timezone.utc)
    post = Post(
        id="p", platform="reddit", url="u", page_title="", post_title="",
        date=dt, author=None, content=None, likes=None, comments=[],
    )
    assert flatten_comments(post) == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_scraping/test_dispatch.py -v
```

Expected: FAIL — `scrape` and `flatten_comments` don't exist.

- [ ] **Step 3: Rewrite `autoso/scraping/__init__.py`**

```python
from autoso.scraping.base import get_scraper
from autoso.scraping.models import Comment, Post
from autoso.storage.supabase import get_recent_scrape, store_scrape


def scrape(url: str) -> tuple[str, Post]:
    """Scrape a URL, returning (scrape_id, Post).

    If a cached scrape for this URL exists within the 30-minute window,
    the cached Post is returned without re-scraping.
    """
    cached = get_recent_scrape(url)
    if cached is not None:
        return cached

    scraper = get_scraper(url)
    post = scraper.scrape(url)
    scrape_id = store_scrape(url, post)
    return scrape_id, post


def flatten_comments(post: Post) -> list[Comment]:
    """Return all comments and nested subcomments in depth-first order."""
    out: list[Comment] = []
    for c in post.comments:
        _walk(c, out)
    return out


def _walk(c: Comment, out: list[Comment]) -> None:
    out.append(c)
    for sub in c.subcomments:
        _walk(sub, out)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_scraping/test_dispatch.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add autoso/scraping/__init__.py tests/test_scraping/test_dispatch.py
git commit -m "feat(scraping): unified scrape() with Supabase cache and flatten_comments helper"
```

---

## Task 11: Pipeline Integration — Use scrape() and flatten_comments

**Files:**
- Modify: `autoso/pipeline/pipeline.py`
- Modify: `tests/test_pipeline/test_pipeline.py`

- [ ] **Step 1: Read the existing pipeline test**

```bash
cat tests/test_pipeline/test_pipeline.py
```

Note any patches to `autoso.scraping.base.get_scraper` — those need replacing with patches to `autoso.scraping.scrape`.

- [ ] **Step 2: Update `autoso/pipeline/pipeline.py`**

Replace the scraping + comment-indexing section of `run_pipeline`. The whole new function:

```python
# autoso/pipeline/pipeline.py
import logging
from dataclasses import dataclass, field
from typing import List, Literal, Optional

from autoso.pipeline.citation import (
    CitationNode,
    build_citation_engine,
    extract_citations,
    strip_citation_markers,
)
from autoso.pipeline.holy_grail import load_holy_grail
from autoso.pipeline.indexer import index_comments
from autoso.pipeline.llm import configure_llm
from autoso.pipeline.prompts import (
    BUCKET_FORMAT_INSTRUCTION,
    BUCKET_SYSTEM_PROMPT,
    TEXTURE_FORMAT_INSTRUCTION,
    TEXTURE_SYSTEM_PROMPT,
)
from autoso.pipeline.title import infer_title
from autoso.scraping import flatten_comments, scrape
from autoso.storage.supabase import store_result

logger = logging.getLogger(__name__)

Mode = Literal["texture", "bucket"]


@dataclass
class PipelineResult:
    title: str
    output: str
    output_cited: str
    citation_index: List[CitationNode] = field(default_factory=list)
    run_id: str = ""


def run_pipeline(
    url: str,
    mode: Mode,
    provided_title: Optional[str] = None,
) -> PipelineResult:
    configure_llm()

    scrape_id, post = scrape(url)
    all_comments = flatten_comments(post)
    logger.info("Scraped %d comments from %s", len(all_comments), post.platform)

    if not all_comments:
        raise RuntimeError(
            f"No comments retrieved from {url}. "
            f"The scraper returned 0 comments — check session cookies, "
            f"proxy, or whether the post has comments."
        )

    title = provided_title or infer_title(post)

    comment_index = index_comments(all_comments)

    comments_text = "\n".join(
        f"Comment {c.position}: {c.text}" for c in all_comments
    )
    post_context = (
        f"{post.platform.upper()} POST:\n{post.content}\n\n"
        f"COMMENTS:\n{comments_text}"
    )

    if mode == "texture":
        system = TEXTURE_SYSTEM_PROMPT
        format_instr = TEXTURE_FORMAT_INSTRUCTION.format(title=title)
        full_query = f"{post_context}\n\n{format_instr}"
    else:
        system = BUCKET_SYSTEM_PROMPT
        holy_grail_index = load_holy_grail()
        hg_engine = build_citation_engine(holy_grail_index, similarity_top_k=20)
        hg_response = hg_engine.query(
            "List all bucket labels for MINDEF/SAF/NS/Defence sentiment analysis"
        )
        format_instr = BUCKET_FORMAT_INSTRUCTION.format(title=title)
        full_query = (
            f"{post_context}\n\n"
            f"BUCKET HOLY GRAIL REFERENCE:\n{hg_response}\n\n"
            f"{format_instr}"
        )

    comment_engine = build_citation_engine(comment_index, system_prompt=system)

    response = comment_engine.query(full_query)

    output_cited = str(response)
    output_clean = strip_citation_markers(output_cited)

    citations = extract_citations(response)

    run_id = store_result(
        url=url,
        mode=mode,
        title=title,
        output=output_clean,
        output_cited=output_cited,
        citation_index=[
            {
                "citation_number": c.citation_number,
                "text": c.text,
                "platform": c.platform,
                "comment_id": c.id,
                "position": c.position,
            }
            for c in citations
        ],
        scrape_id=scrape_id,
    )

    return PipelineResult(
        title=title,
        output=output_clean,
        output_cited=output_cited,
        citation_index=citations,
        run_id=run_id,
    )
```

- [ ] **Step 3: Update `tests/test_pipeline/test_pipeline.py`**

Search the file for every occurrence of `get_scraper` and replace with patches targeting `autoso.pipeline.pipeline.scrape`. The mocked `scrape` must return a tuple `(scrape_id, Post)`. Example migration pattern:

Before:
```python
@patch("autoso.pipeline.pipeline.get_scraper")
def test_run_pipeline(mock_factory, ...):
    mock_scraper = MagicMock()
    mock_scraper.scrape.return_value = Post(title="T", content="C", url="u",
                                            platform="reddit", comments=[...])
    mock_factory.return_value = mock_scraper
```

After:
```python
@patch("autoso.pipeline.pipeline.scrape")
def test_run_pipeline(mock_scrape, ...):
    mock_scrape.return_value = ("sid-1", Post(
        id="p", platform="reddit", url="u",
        page_title="r/t", post_title="T",
        date=None, author=None, content="C", likes=None,
        comments=[Comment(id="c1", platform="reddit", author=None, date=None,
                          text="hi", likes=None, position=0)],
    ))
```

Also: any assertion on `store_result` call args must include `scrape_id="sid-1"` (or whatever value the mock returned).

- [ ] **Step 4: Run pipeline tests to verify they pass**

```bash
pytest tests/test_pipeline/test_pipeline.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add autoso/pipeline/pipeline.py tests/test_pipeline/test_pipeline.py
git commit -m "refactor(pipeline): use unified scrape() and flatten_comments"
```

---

# Step 5: New Scrapers

## Task 12: HardwareZone Scraper

**Files:**
- Create: `autoso/scraping/hardwarezone.py`
- Create: `tests/test_scraping/test_hardwarezone.py`

- [ ] **Step 1: Create `tests/test_scraping/test_hardwarezone.py`**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from autoso.scraping.hardwarezone import HardwareZoneScraper
from autoso.scraping.models import Post


@pytest.mark.asyncio
@patch("autoso.scraping.hardwarezone.async_playwright")
@patch("autoso.scraping.hardwarezone.stealth_async", new_callable=AsyncMock)
async def test_scrape_returns_post_empty_when_no_posts(mock_stealth, mock_pw):
    scraper = HardwareZoneScraper()

    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = MagicMock()
    mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_pw.return_value)
    mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_pw.return_value.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.storage_state = AsyncMock(return_value={})

    mock_page.goto = AsyncMock()
    mock_page.url = "https://forums.hardwarezone.com.sg/threads/foo.1/"
    mock_page.content = AsyncMock(return_value="<html></html>")

    empty = MagicMock()
    empty.count = AsyncMock(return_value=0)
    empty.is_visible = AsyncMock(return_value=False)
    empty.get_attribute = AsyncMock(return_value=None)
    empty.inner_text = AsyncMock(return_value="")
    empty.first = empty
    empty.nth = MagicMock(return_value=empty)

    mock_page.locator = MagicMock(return_value=empty)
    mock_page.get_by_text = MagicMock(return_value=empty)

    post = await scraper._scrape_async("https://forums.hardwarezone.com.sg/threads/foo.1/")
    assert isinstance(post, Post)
    assert post.platform == "hardwarezone"
    assert post.comments == []


@pytest.mark.asyncio
@patch("autoso.scraping.hardwarezone.async_playwright")
@patch("autoso.scraping.hardwarezone.stealth_async", new_callable=AsyncMock)
async def test_scrape_follows_pagination(mock_stealth, mock_pw):
    """Pagination loop must stop when next-page link is not visible."""
    scraper = HardwareZoneScraper()

    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = MagicMock()
    mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_pw.return_value)
    mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_pw.return_value.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.storage_state = AsyncMock(return_value={})

    mock_page.goto = AsyncMock()
    mock_page.url = "https://forums.hardwarezone.com.sg/threads/foo.1/"
    mock_page.content = AsyncMock(return_value="<html></html>")

    empty = MagicMock()
    empty.count = AsyncMock(return_value=0)
    empty.is_visible = AsyncMock(return_value=False)
    empty.get_attribute = AsyncMock(return_value=None)
    empty.inner_text = AsyncMock(return_value="")
    empty.first = empty
    empty.nth = MagicMock(return_value=empty)

    mock_page.locator = MagicMock(return_value=empty)
    mock_page.get_by_text = MagicMock(return_value=empty)

    post = await scraper._scrape_async("https://forums.hardwarezone.com.sg/threads/foo.1/")

    # goto called exactly once because no next-page link is visible
    assert mock_page.goto.call_count == 1
    assert post.comments == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_scraping/test_hardwarezone.py -v
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Create `autoso/scraping/hardwarezone.py`**

```python
import asyncio
import re
from datetime import datetime
from typing import List
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from autoso.scraping.playwright_base import PlaywrightScraper
from autoso.scraping.models import Comment, Post, ScrapeError


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
            position = 0

            # Page 1 comments = posts after the first
            comments_page_1 = await self._extract_comments_on_page(page, start_position=0)
            all_comments.extend(comments_page_1)
            position = len(all_comments)

            # Follow pagination: max 50 pages safety cap
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
                page_comments = await self._extract_comments_on_page(page, start_position=position)
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
        """Read the first `.message` container on the thread page."""
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
        """Return every reply post on the current page, skipping the first one on page 1."""
        msgs = page.locator("article.message")
        count = await msgs.count()
        comments: List[Comment] = []
        # On the first pagination page, skip the first message (it's the thread OP == post body)
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
        from urllib.parse import urlparse
        parts = urlparse(base)
        return f"{parts.scheme}://{parts.netloc}{href}"
    # relative
    from urllib.parse import urljoin
    return urljoin(base, href)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_scraping/test_hardwarezone.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add autoso/scraping/hardwarezone.py tests/test_scraping/test_hardwarezone.py
git commit -m "feat(hardwarezone): new scraper with pagination support"
```

---

## Task 13: YouTube Scraper (yt-dlp)

**Files:**
- Create: `autoso/scraping/youtube.py`
- Create: `tests/test_scraping/test_youtube.py`

- [ ] **Step 1: Create `tests/test_scraping/test_youtube.py`**

```python
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from autoso.scraping.youtube import YouTubeScraper
from autoso.scraping.models import Post, ScrapeError


def _fake_info_json(tmp_path: Path, data: dict) -> Path:
    info = tmp_path / "abc123.info.json"
    info.write_text(json.dumps(data))
    return info


@patch("autoso.scraping.youtube.subprocess.run")
@patch("autoso.scraping.youtube.tempfile.mkdtemp")
def test_scrape_parses_info_json(mock_mkdtemp, mock_run, tmp_path):
    mock_mkdtemp.return_value = str(tmp_path)
    data = {
        "id": "abc123",
        "title": "Test Video",
        "description": "Video body",
        "channel": "MINDEF",
        "upload_date": "20260418",
        "like_count": 100,
        "comments": [
            {"id": "c1", "author": "u1", "text": "Top", "timestamp": 1713436800,
             "like_count": 5, "parent": "root"},
            {"id": "r1", "author": "u2", "text": "Reply", "timestamp": 1713436900,
             "like_count": 1, "parent": "c1"},
            {"id": "c2", "author": "u3", "text": "Second top", "timestamp": 1713437000,
             "like_count": 3, "parent": "root"},
        ],
    }
    _fake_info_json(tmp_path, data)
    mock_run.return_value = MagicMock(returncode=0, stderr="")

    scraper = YouTubeScraper()
    post = scraper.scrape("https://www.youtube.com/watch?v=abc123")

    assert isinstance(post, Post)
    assert post.platform == "youtube"
    assert post.id == "abc123"
    assert post.post_title == "Test Video"
    assert post.author == "MINDEF"
    assert post.likes == 100
    assert post.content == "Video body"
    assert post.date is not None
    # Top-level comments
    assert len(post.comments) == 2
    assert post.comments[0].id == "c1"
    assert post.comments[0].likes == 5
    assert len(post.comments[0].subcomments) == 1
    assert post.comments[0].subcomments[0].id == "r1"
    assert post.comments[1].id == "c2"
    assert post.comments[1].subcomments == []


@patch("autoso.scraping.youtube.subprocess.run")
@patch("autoso.scraping.youtube.tempfile.mkdtemp")
def test_scrape_raises_on_yt_dlp_error(mock_mkdtemp, mock_run, tmp_path):
    mock_mkdtemp.return_value = str(tmp_path)
    mock_run.return_value = MagicMock(returncode=1, stderr="video unavailable")

    scraper = YouTubeScraper()
    with pytest.raises(ScrapeError):
        scraper.scrape("https://www.youtube.com/watch?v=x")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_scraping/test_youtube.py -v
```

Expected: FAIL.

- [ ] **Step 3: Create `autoso/scraping/youtube.py`**

```python
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autoso.scraping.models import Comment, Post, ScrapeError


_YT_DLP_TIMEOUT = 300


class YouTubeScraper:
    def scrape(self, url: str) -> Post:
        output_dir = tempfile.mkdtemp()
        output_template = str(Path(output_dir) / "%(id)s")

        result = subprocess.run(
            [
                "yt-dlp",
                "--skip-download",
                "--write-info-json",
                "--write-comments",
                "--no-warnings",
                "-o", output_template,
                url,
            ],
            capture_output=True,
            text=True,
            timeout=_YT_DLP_TIMEOUT,
        )
        if result.returncode != 0:
            raise ScrapeError(
                f"yt-dlp failed: {result.stderr.strip()}", cause="unknown"
            )

        info_files = list(Path(output_dir).glob("*.info.json"))
        if not info_files:
            raise ScrapeError(
                f"No .info.json emitted by yt-dlp in {output_dir}",
                cause="selector_drift",
            )
        with open(info_files[0]) as f:
            data = json.load(f)

        return _build_post(url, data)


def _build_post(url: str, data: dict[str, Any]) -> Post:
    comments_flat = data.get("comments") or []
    comments = _nest_comments(comments_flat)

    return Post(
        id=data.get("id", ""),
        platform="youtube",
        url=url,
        page_title=data.get("channel") or "YouTube",
        post_title=data.get("title", ""),
        date=_parse_upload_date(data.get("upload_date")),
        author=data.get("channel"),
        content=data.get("description", ""),
        likes=data.get("like_count"),
        comments=comments,
    )


def _parse_upload_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _nest_comments(raw: list[dict[str, Any]]) -> list[Comment]:
    """Turn a flat list with `parent` pointers into a nested tree.
    Top-level comments have parent == 'root'."""
    by_id: dict[str, Comment] = {}
    top_level: list[Comment] = []
    top_pos = 0

    # First pass: build Comment objects
    for raw_c in raw:
        c = Comment(
            id=str(raw_c.get("id", "")),
            platform="youtube",
            author=raw_c.get("author"),
            date=_epoch_to_dt(raw_c.get("timestamp")),
            text=raw_c.get("text", ""),
            likes=raw_c.get("like_count"),
            position=0,  # reassigned below
        )
        by_id[c.id] = c

    # Second pass: nest
    for raw_c in raw:
        cid = str(raw_c.get("id", ""))
        parent = raw_c.get("parent", "root")
        comment = by_id[cid]
        if parent == "root" or parent not in by_id:
            comment.position = top_pos
            top_level.append(comment)
            top_pos += 1
        else:
            by_id[parent].subcomments.append(comment)

    return top_level


def _epoch_to_dt(epoch: float | None) -> datetime | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_scraping/test_youtube.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add autoso/scraping/youtube.py tests/test_scraping/test_youtube.py
git commit -m "feat(youtube): new scraper using yt-dlp to fetch video metadata and comments"
```

---

## Task 14: TikTok Scraper

**Files:**
- Create: `autoso/scraping/tiktok.py`
- Create: `tests/test_scraping/test_tiktok.py`

- [ ] **Step 1: Create `tests/test_scraping/test_tiktok.py`**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from autoso.scraping.tiktok import TikTokScraper, _extract_from_payload
from autoso.scraping.models import Post


def test_extract_from_payload_builds_nested_comments():
    payload = {
        "comments": [
            {
                "cid": "c1", "text": "First", "nickname": "user1",
                "create_time": 1713436800, "digg_count": 5,
                "reply_comment": [
                    {"cid": "r1", "text": "Reply", "nickname": "user2",
                     "create_time": 1713436900, "digg_count": 1},
                ],
            },
            {
                "cid": "c2", "text": "Second", "nickname": "user3",
                "create_time": 1713437000, "digg_count": 3,
                "reply_comment": [],
            },
        ],
    }
    comments = _extract_from_payload(payload, start_position=0)
    assert len(comments) == 2
    assert comments[0].id == "c1"
    assert comments[0].text == "First"
    assert comments[0].likes == 5
    assert len(comments[0].subcomments) == 1
    assert comments[0].subcomments[0].id == "r1"
    assert comments[1].subcomments == []


@pytest.mark.asyncio
@patch("autoso.scraping.tiktok.async_playwright")
@patch("autoso.scraping.tiktok.stealth_async", new_callable=AsyncMock)
async def test_scrape_empty_when_no_xhr_intercepted(mock_stealth, mock_pw):
    scraper = TikTokScraper()
    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = MagicMock()
    mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_pw.return_value)
    mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_pw.return_value.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.storage_state = AsyncMock(return_value={})

    mock_page.goto = AsyncMock()
    mock_page.url = "https://www.tiktok.com/@mindef/video/123"
    mock_page.content = AsyncMock(return_value="<html></html>")
    mock_page.on = MagicMock()
    mock_page.evaluate = AsyncMock(return_value=None)

    empty = MagicMock()
    empty.is_visible = AsyncMock(return_value=False)
    empty.get_attribute = AsyncMock(return_value=None)
    empty.inner_text = AsyncMock(return_value="")
    empty.first = empty
    empty.nth = MagicMock(return_value=empty)
    empty.count = AsyncMock(return_value=0)

    mock_page.locator = MagicMock(return_value=empty)

    post = await scraper._scrape_async("https://www.tiktok.com/@mindef/video/123")
    assert isinstance(post, Post)
    assert post.platform == "tiktok"
    assert post.comments == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_scraping/test_tiktok.py -v
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Create `autoso/scraping/tiktok.py`**

```python
import asyncio
import re
from datetime import datetime, timezone
from typing import Any, List
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

from autoso.scraping.playwright_base import PlaywrightScraper
from autoso.scraping.models import Comment, Post, ScrapeError


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
                await page.goto(url, wait_until="networkidle", timeout=30_000)
            except Exception as exc:
                raise ScrapeError(f"Page load failed: {exc}", cause="timeout")

            await self._human_delay(1500, 2500)
            await self._scroll_comments(page)
            await self._human_delay(2000, 4000)  # let final XHRs complete

            post_title = await self._extract_caption(page)
            author = await self._extract_author(page)
            page_title = f"@{author}" if author else "TikTok"
            post_date = await self._extract_post_date(page)
            post_likes = await self._extract_post_likes(page)

            all_comments: List[Comment] = []
            for payload in captured_payloads:
                all_comments.extend(_extract_from_payload(payload, start_position=len(all_comments)))

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
                content=post_title,  # TikTok has no separate body
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
                # "2024-04-18" form
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
    """Build Comment objects from one /api/comment/list payload."""
    raw = payload.get("comments") or []
    out: list[Comment] = []
    for i, rc in enumerate(raw):
        pos = start_position + i
        subs = []
        for j, rr in enumerate(rc.get("reply_comment") or []):
            subs.append(Comment(
                id=str(rr.get("cid", "")),
                platform="tiktok",
                author=rr.get("nickname"),
                date=_epoch_to_dt(rr.get("create_time")),
                text=rr.get("text", ""),
                likes=rr.get("digg_count"),
                position=j,
            ))
        out.append(Comment(
            id=str(rc.get("cid", "")),
            platform="tiktok",
            author=rc.get("nickname"),
            date=_epoch_to_dt(rc.get("create_time")),
            text=rc.get("text", ""),
            likes=rc.get("digg_count"),
            position=pos,
            subcomments=subs,
        ))
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_scraping/test_tiktok.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add autoso/scraping/tiktok.py tests/test_scraping/test_tiktok.py
git commit -m "feat(tiktok): new scraper using XHR interception on /api/comment/list"
```

---

# Step 6: Final Verification

## Task 15: Full Test Suite Pass

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

```bash
pytest -v
```

Expected: All tests pass. The previously deferred `test_get_scraper_returns_correct_type` should now pass because all six scraper modules exist.

If any failures appear: address them inline before proceeding. Common issues:
- Leftover import of `praw` in a test file (remove it)
- Leftover `Comment(comment_id=...)` kwarg in a test (rename to `id=`)
- Pipeline test patching `get_scraper` instead of `scrape`

- [ ] **Step 2: Run a smoke check — detect_platform + scraper construction for all six platforms**

```bash
python -c "
from autoso.scraping.base import get_scraper
for u in [
    'https://reddit.com/r/x/comments/y',
    'https://instagram.com/p/ABC/',
    'https://facebook.com/m/posts/1',
    'https://forums.hardwarezone.com.sg/threads/a.1/',
    'https://youtube.com/watch?v=a',
    'https://tiktok.com/@u/video/1',
]:
    print(u, '->', type(get_scraper(u)).__name__)
"
```

Expected: all six print without error, each emitting the matching scraper class name.

- [ ] **Step 3: Commit the plan file itself (if not already committed)**

```bash
git status
```

If the plan file is listed as untracked, add and commit it.

---

# Notes for the Implementer

- **Supabase migration must be applied manually** in the Supabase SQL Editor before running the updated code against a real DB. The `TRUNCATE` in `003_scrapes_table.sql` will wipe all prior analyses and citations.
- **Environment variables**: after Task 6, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT` can be removed from `.env`. Keep them if you want to avoid breaking local envs that still have them (ignoring unused env vars is harmless).
- **yt-dlp binary** is already installed via `pyproject.toml`'s `yt-dlp` dependency (used by transcription). The YouTube scraper invokes it via `subprocess`, matching the pattern of `autoso/transcription/downloader.py`.
- **Playwright selectors** in Facebook / Instagram / HardwareZone / TikTok are known to be fragile. A live smoke test after deployment is expected — extraction may return `None` for author/date/likes when selectors drift, which is intended behaviour (fields are Optional).
- **Session cookies** for FB / IG / HardwareZone / TikTok live under `data/sessions/<platform>_session.json`. First runs on a fresh environment will require manual login via the Playwright browser.
