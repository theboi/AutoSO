# AutoSO Phase 1Y — LLM Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Multi-URL `/texture` and `/bucket` analyses with a user-selectable analysis mode (`prompt` default = direct Anthropic SDK with all comments inline; `rag` alternative = existing `CitationQueryEngine`), scaled comment pool up to 5000, and a schema rework that makes every citation traceable to its source URL and scrape record.

**Architecture:** A new `flatten → pool → analyse → store` pipeline replaces the current single-URL flow. Flattening serialises each thread into `FlatComment`s (parent + up to 9 replies, with `thread_context`); pooling concatenates across URLs and assigns 1-based citation numbers. Two analysis modules share an `AnalysisResult` contract: `prompt_analysis` calls `anthropic.messages.create` with the pool rendered inline, `rag_analysis` indexes the flat pool and uses `CitationQueryEngine` with `similarity_top_k=len(pool)`. Storage inserts one `analyses` row, one `analysis_sources` row per URL, and one `citations` row per cited comment. Bucket mode runs Holy Grail retrieval once in `run_pipeline` and passes the HG block into whichever analysis module is selected.

**Tech Stack:** Python 3.11, `anthropic` SDK, `llama-index` (`CitationQueryEngine`, ChromaDB `EphemeralClient`, HF embeddings), `supabase-py`, `python-telegram-bot`, pytest.

**Spec:** [docs/superpowers/specs/2026-04-19-phase-1y-llm-improvements-design.md](../specs/2026-04-19-phase-1y-llm-improvements-design.md)

---

## File Map

**Created:**
- `migrations/004_multi_url_analysis.sql`
- `autoso/pipeline/scaling.py`
- `autoso/pipeline/flatten.py`
- `autoso/pipeline/pool.py`
- `autoso/pipeline/analysis.py` (shared `CitationRecord`, `AnalysisResult`)
- `autoso/pipeline/prompt_analysis.py`
- `autoso/pipeline/rag_analysis.py`
- `tests/test_pipeline/test_scaling.py`
- `tests/test_pipeline/test_flatten.py`
- `tests/test_pipeline/test_pool.py`
- `tests/test_pipeline/test_prompt_analysis.py`
- `tests/test_pipeline/test_rag_analysis.py`
- `tests/test_storage/__init__.py`
- `tests/test_storage/test_supabase_multi.py`

**Modified:**
- `autoso/pipeline/citation.py` (drop `CitationNode` + `extract_citations`, add `citation_chunk_size` kwarg)
- `autoso/pipeline/prompts.py` (drop `CRITICAL: Do NOT include citation markers` line, add multi-source hint)
- `autoso/pipeline/pipeline.py` (rewrite `run_pipeline` for list-of-urls + analysis_mode; Holy Grail moved up)
- `autoso/storage/supabase.py` (replace `store_result` with `store_multi_result`)
- `autoso/bot/handlers.py` (new `_parse_analysis_args`; `/start` text; `_handle_analysis` passes list + mode)
- `tests/test_pipeline/test_pipeline.py` (update to list-of-urls signature)
- `tests/test_pipeline/test_citation.py` (remove `CitationNode`/`extract_citations` tests)
- `tests/test_bot/test_handlers.py` (remove `CitationNode` import; new parser tests)
- `tests/integration/test_analyze.py` (call sites use list-of-urls)

---

## Task 1: Schema migration

**Files:**
- Create: `migrations/004_multi_url_analysis.sql`

- [ ] **Step 1: Write migration SQL**

Write `migrations/004_multi_url_analysis.sql`:

```sql
-- Phase 1Y: multi-URL analyses.
-- Existing analyses rows are wiped (small DB, shape changed too much to backfill).

TRUNCATE TABLE citations, analyses RESTART IDENTITY CASCADE;

ALTER TABLE analyses DROP COLUMN url;

ALTER TABLE analyses
    ADD COLUMN analysis_mode TEXT NOT NULL DEFAULT 'prompt'
    CHECK (analysis_mode IN ('prompt', 'rag'));

CREATE TABLE IF NOT EXISTS analysis_sources (
    id          UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID    NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    url         TEXT    NOT NULL,
    link_index  INTEGER NOT NULL,
    scrape_id   UUID    REFERENCES scrapes(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_analysis_sources_analysis_id
    ON analysis_sources (analysis_id);

ALTER TABLE citations
    ADD COLUMN source_id UUID REFERENCES analysis_sources(id);
ALTER TABLE citations DROP COLUMN platform;
ALTER TABLE citations
    ADD CONSTRAINT citations_run_citation_unique UNIQUE (run_id, citation_number);
```

- [ ] **Step 2: Commit**

```bash
git add migrations/004_multi_url_analysis.sql
git commit -m "feat(db): migration 004 — multi-URL analysis schema"
```

Migration is applied manually in the Supabase SQL editor at deploy time (handled in Task 22).

---

## Task 2: Scaling function

**Files:**
- Create: `autoso/pipeline/scaling.py`
- Test: `tests/test_pipeline/test_scaling.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_pipeline/test_scaling.py`:

```python
import pytest

from autoso.pipeline.scaling import comments_per_link


def test_single_link_returns_500():
    assert comments_per_link(1) == 500


def test_ten_links_returns_500_each():
    assert comments_per_link(10) == 500


def test_eleven_links_scales_down():
    # 5000 // 11 = 454
    assert comments_per_link(11) == 454


def test_twenty_links_returns_250():
    assert comments_per_link(20) == 250


def test_fifty_links_returns_100():
    assert comments_per_link(50) == 100


def test_zero_links_raises():
    with pytest.raises(ValueError):
        comments_per_link(0)


def test_negative_links_raises():
    with pytest.raises(ValueError):
        comments_per_link(-3)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pipeline/test_scaling.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'autoso.pipeline.scaling'`.

- [ ] **Step 3: Implement**

Create `autoso/pipeline/scaling.py`:

```python
# autoso/pipeline/scaling.py
"""Per-link comment cap with total-pool scaling."""


def comments_per_link(num_links: int) -> int:
    """Max flattened comments per link.

    Returns 500 for 1–10 links (total ≤ 5000). Above 10 links, scales down
    to hold the total pool at ~5000.
    """
    if num_links <= 0:
        raise ValueError("num_links must be >= 1")
    if num_links <= 10:
        return 500
    return 5000 // num_links
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pipeline/test_scaling.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add autoso/pipeline/scaling.py tests/test_pipeline/test_scaling.py
git commit -m "feat(pipeline): add comments_per_link scaling"
```

---

## Task 3: FlatComment + top-level flattening

**Files:**
- Create: `autoso/pipeline/flatten.py`
- Test: `tests/test_pipeline/test_flatten.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_pipeline/test_flatten.py`:

```python
from autoso.pipeline.flatten import FlatComment, flatten_post_comments
from autoso.scraping.models import Comment, Post


def _comment(id_: str, text: str, position: int, replies=None) -> Comment:
    return Comment(
        id=id_,
        platform="facebook",
        author=None,
        date=None,
        text=text,
        likes=None,
        position=position,
        subcomments=list(replies or []),
    )


def _post(comments: list[Comment]) -> Post:
    return Post(
        id="p1",
        platform="facebook",
        url="https://facebook.com/x",
        page_title="pg",
        post_title="pt",
        date=None,
        author=None,
        content="c",
        likes=None,
        comments=comments,
    )


def test_single_top_level_no_replies():
    post = _post([_comment("a", "alpha", 0)])

    result = flatten_post_comments(post, n_cap=500, source_index=0)

    assert len(result) == 1
    assert result[0] == FlatComment(
        original_id="a",
        position=0,
        text="alpha",
        thread_context=[],
        source_index=0,
    )


def test_multiple_top_level_no_replies():
    post = _post([
        _comment("a", "alpha", 0),
        _comment("b", "bravo", 1),
        _comment("c", "charlie", 2),
    ])

    result = flatten_post_comments(post, n_cap=500, source_index=3)

    assert [r.text for r in result] == ["alpha", "bravo", "charlie"]
    assert all(r.thread_context == [] for r in result)
    assert all(r.source_index == 3 for r in result)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pipeline/test_flatten.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement minimal version**

Create `autoso/pipeline/flatten.py`:

```python
# autoso/pipeline/flatten.py
"""Flatten a Post's comments into a list of FlatComment for LLM consumption."""
from __future__ import annotations

from dataclasses import dataclass, field

from autoso.scraping.models import Comment, Post

MAX_THREAD_MESSAGES = 10  # parent + up to 9 replies


@dataclass
class FlatComment:
    original_id: str          # Comment.id from the scrape
    position: int             # 0-indexed within this flattened list
    text: str                 # this comment's own text, no prepend
    thread_context: list[str] = field(default_factory=list)
    source_index: int = 0     # which URL in the user-provided order


def flatten_post_comments(
    post: Post, n_cap: int, source_index: int
) -> list[FlatComment]:
    out: list[FlatComment] = []
    for top in post.comments:
        if len(out) >= n_cap:
            break
        out.append(
            FlatComment(
                original_id=top.id,
                position=len(out),
                text=top.text,
                thread_context=[],
                source_index=source_index,
            )
        )
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pipeline/test_flatten.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add autoso/pipeline/flatten.py tests/test_pipeline/test_flatten.py
git commit -m "feat(pipeline): FlatComment + top-level flattening"
```

---

## Task 4: Flattening — replies with thread_context

**Files:**
- Modify: `autoso/pipeline/flatten.py`
- Modify: `tests/test_pipeline/test_flatten.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_pipeline/test_flatten.py`:

```python
def test_parent_with_three_replies_builds_thread_context():
    post = _post([
        _comment("p", "parent", 0, replies=[
            _comment("r1", "reply1", 0),
            _comment("r2", "reply2", 1),
            _comment("r3", "reply3", 2),
        ]),
    ])

    result = flatten_post_comments(post, n_cap=500, source_index=0)

    assert [r.text for r in result] == ["parent", "reply1", "reply2", "reply3"]
    assert result[0].thread_context == []
    assert result[1].thread_context == ["parent"]
    assert result[2].thread_context == ["parent", "reply1"]
    assert result[3].thread_context == ["parent", "reply1", "reply2"]
    assert [r.position for r in result] == [0, 1, 2, 3]


def test_reply_text_has_no_prepend():
    """thread_context is a separate field; the .text is only the reply's own body."""
    post = _post([
        _comment("p", "parent", 0, replies=[_comment("r1", "the actual reply", 0)]),
    ])

    result = flatten_post_comments(post, n_cap=500, source_index=0)

    assert result[1].text == "the actual reply"
    assert "parent" not in result[1].text
```

- [ ] **Step 2: Run tests to verify new ones fail**

Run: `pytest tests/test_pipeline/test_flatten.py -v`
Expected: 2 new tests FAIL (only top-level is emitted today); old 2 still pass.

- [ ] **Step 3: Extend implementation**

In `autoso/pipeline/flatten.py`, replace the loop body inside `flatten_post_comments`:

```python
def flatten_post_comments(
    post: Post, n_cap: int, source_index: int
) -> list[FlatComment]:
    out: list[FlatComment] = []
    for top in post.comments:
        if len(out) >= n_cap:
            break
        out.append(
            FlatComment(
                original_id=top.id,
                position=len(out),
                text=top.text,
                thread_context=[],
                source_index=source_index,
            )
        )
        running_context: list[str] = [top.text]
        for reply in top.subcomments:
            if len(out) >= n_cap:
                break
            out.append(
                FlatComment(
                    original_id=reply.id,
                    position=len(out),
                    text=reply.text,
                    thread_context=list(running_context),
                    source_index=source_index,
                )
            )
            running_context.append(reply.text)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pipeline/test_flatten.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add autoso/pipeline/flatten.py tests/test_pipeline/test_flatten.py
git commit -m "feat(pipeline): flatten replies with thread_context"
```

---

## Task 5: Flattening — 10-message thread cap

**Files:**
- Modify: `autoso/pipeline/flatten.py`
- Modify: `tests/test_pipeline/test_flatten.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_pipeline/test_flatten.py`:

```python
def test_thread_caps_at_10_messages_parent_plus_9_replies():
    replies = [_comment(f"r{i}", f"reply{i}", i) for i in range(12)]
    post = _post([_comment("p", "parent", 0, replies=replies)])

    result = flatten_post_comments(post, n_cap=500, source_index=0)

    # parent + 9 replies = 10 messages; reply10 and reply11 dropped
    assert len(result) == 10
    assert [r.text for r in result] == (
        ["parent"] + [f"reply{i}" for i in range(9)]
    )
    # Last emitted reply has 9 items in thread_context (parent + 8 prior replies)
    assert len(result[-1].thread_context) == 9


def test_next_top_level_visited_after_capped_thread():
    """A thread hitting the 10-cap does NOT stop the outer loop."""
    replies = [_comment(f"r{i}", f"reply{i}", i) for i in range(15)]
    post = _post([
        _comment("p1", "parent1", 0, replies=replies),
        _comment("p2", "parent2", 1),
    ])

    result = flatten_post_comments(post, n_cap=500, source_index=0)

    texts = [r.text for r in result]
    assert texts[:10] == ["parent1"] + [f"reply{i}" for i in range(9)]
    assert texts[10] == "parent2"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pipeline/test_flatten.py -v`
Expected: 2 new tests FAIL.

- [ ] **Step 3: Extend implementation**

In `autoso/pipeline/flatten.py`, change the reply loop to stop after 9 replies:

```python
        running_context: list[str] = [top.text]
        for reply in top.subcomments[: MAX_THREAD_MESSAGES - 1]:
            if len(out) >= n_cap:
                break
            out.append(
                FlatComment(
                    original_id=reply.id,
                    position=len(out),
                    text=reply.text,
                    thread_context=list(running_context),
                    source_index=source_index,
                )
            )
            running_context.append(reply.text)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pipeline/test_flatten.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add autoso/pipeline/flatten.py tests/test_pipeline/test_flatten.py
git commit -m "feat(pipeline): cap flattened threads at 10 messages"
```

---

## Task 6: Flattening — n_cap truncation and empty post

**Files:**
- Modify: `tests/test_pipeline/test_flatten.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_pipeline/test_flatten.py`:

```python
def test_n_cap_truncates_mid_thread():
    replies = [_comment(f"r{i}", f"reply{i}", i) for i in range(5)]
    post = _post([
        _comment("p1", "parent1", 0, replies=replies),
        _comment("p2", "parent2", 1),
    ])

    result = flatten_post_comments(post, n_cap=3, source_index=0)

    # 3 emitted: parent1, reply0, reply1; nothing from p2
    assert [r.text for r in result] == ["parent1", "reply0", "reply1"]


def test_empty_post():
    post = _post([])

    result = flatten_post_comments(post, n_cap=500, source_index=0)

    assert result == []


def test_source_index_propagates():
    post = _post([
        _comment("p", "parent", 0, replies=[_comment("r1", "reply", 0)]),
    ])

    result = flatten_post_comments(post, n_cap=500, source_index=7)

    assert all(r.source_index == 7 for r in result)
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/test_pipeline/test_flatten.py -v`
Expected: 9 passed. (The implementation from Task 5 already handles these — they are regression guards.)

- [ ] **Step 3: Commit**

```bash
git add tests/test_pipeline/test_flatten.py
git commit -m "test(pipeline): n_cap truncation and edge cases"
```

---

## Task 7: Pool assembly

**Files:**
- Create: `autoso/pipeline/pool.py`
- Test: `tests/test_pipeline/test_pool.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_pipeline/test_pool.py`:

```python
from autoso.pipeline.flatten import FlatComment
from autoso.pipeline.pool import Pool, PoolItem, build_pool
from autoso.scraping.models import Post


def _flat(id_: str, pos: int, src: int, text: str = "x") -> FlatComment:
    return FlatComment(
        original_id=id_, position=pos, text=text, thread_context=[], source_index=src,
    )


def _post(url: str) -> Post:
    return Post(
        id=url, platform="facebook", url=url,
        page_title="", post_title="", date=None, author=None,
        content="", likes=None, comments=[],
    )


def test_build_pool_single_source_numbers_from_one():
    flat_lists = [[_flat("a", 0, 0), _flat("b", 1, 0)]]
    posts = [_post("https://a.com")]

    pool = build_pool(flat_lists, posts)

    assert isinstance(pool, Pool)
    assert len(pool.items) == 2
    assert pool.items[0].citation_number == 1
    assert pool.items[1].citation_number == 2


def test_build_pool_multi_source_continues_numbering():
    flat_lists = [
        [_flat("a", 0, 0), _flat("b", 1, 0)],
        [_flat("c", 0, 1), _flat("d", 1, 1), _flat("e", 2, 1)],
    ]
    posts = [_post("https://a.com"), _post("https://b.com")]

    pool = build_pool(flat_lists, posts)

    assert [i.citation_number for i in pool.items] == [1, 2, 3, 4, 5]
    assert [i.flat.source_index for i in pool.items] == [0, 0, 1, 1, 1]


def test_lookup_by_citation_number():
    flat_lists = [[_flat("a", 0, 0)], [_flat("b", 0, 1)]]
    posts = [_post("https://a.com"), _post("https://b.com")]

    pool = build_pool(flat_lists, posts)

    assert pool.lookup(1).flat.original_id == "a"
    assert pool.lookup(2).flat.original_id == "b"


def test_lookup_unknown_citation_returns_none():
    pool = build_pool([[_flat("a", 0, 0)]], [_post("https://a.com")])
    assert pool.lookup(999) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pipeline/test_pool.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `autoso/pipeline/pool.py`:

```python
# autoso/pipeline/pool.py
"""Cross-source pool of flattened comments with global 1-based citation numbers."""
from __future__ import annotations

from dataclasses import dataclass, field

from autoso.pipeline.flatten import FlatComment
from autoso.scraping.models import Post


@dataclass
class PoolItem:
    citation_number: int    # 1-indexed, unique across the pool
    flat: FlatComment


@dataclass
class Pool:
    items: list[PoolItem] = field(default_factory=list)
    posts: list[Post] = field(default_factory=list)

    def lookup(self, citation_number: int) -> PoolItem | None:
        for item in self.items:
            if item.citation_number == citation_number:
                return item
        return None


def build_pool(
    flattened_per_link: list[list[FlatComment]], posts: list[Post]
) -> Pool:
    items: list[PoolItem] = []
    n = 1
    for flat_list in flattened_per_link:
        for flat in flat_list:
            items.append(PoolItem(citation_number=n, flat=flat))
            n += 1
    return Pool(items=items, posts=list(posts))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pipeline/test_pool.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add autoso/pipeline/pool.py tests/test_pipeline/test_pool.py
git commit -m "feat(pipeline): Pool + build_pool with global citation numbers"
```

---

## Task 8: Prompts — drop CRITICAL line, add multi-source hint

**Files:**
- Modify: `autoso/pipeline/prompts.py`

- [ ] **Step 1: Edit TEXTURE_FORMAT_INSTRUCTION**

In `autoso/pipeline/prompts.py`, replace:

```python
TEXTURE_FORMAT_INSTRUCTION = """\
Format your response EXACTLY as follows (replace placeholders):

*{title}*

- X% opined that...
- Y% discussed...
- Z% criticised...
- N comments opined that <SAF/MINDEF/NS/defence mention>
- The rest (~X%) are frivolous

CRITICAL: Do NOT include citation markers such as [1], [2], [N] anywhere in your output.\
"""
```

with:

```python
TEXTURE_FORMAT_INSTRUCTION = """\
When multiple sources are provided, the percentages reflect the combined comment pool across all sources.

Format your response EXACTLY as follows (replace placeholders):

*{title}*

- X% opined that...
- Y% discussed...
- Z% criticised...
- N comments opined that <SAF/MINDEF/NS/defence mention>
- The rest (~X%) are frivolous\
"""
```

- [ ] **Step 2: Edit BUCKET_FORMAT_INSTRUCTION**

Replace:

```python
BUCKET_FORMAT_INSTRUCTION = """\
Format your response EXACTLY as follows (replace placeholders):

*{title}*

*Positive*
1.  Praised...
2.  Opined that...

*Neutral*
1.  Discussed...

*Negative*
1.  Criticised...

Pre-emptives are pos X, neu Y, neg Z

CRITICAL: Do NOT include citation markers such as [1], [2], [N] anywhere in your output.\
"""
```

with:

```python
BUCKET_FORMAT_INSTRUCTION = """\
When multiple sources are provided, the percentages reflect the combined comment pool across all sources.

Format your response EXACTLY as follows (replace placeholders):

*{title}*

*Positive*
1.  Praised...
2.  Opined that...

*Neutral*
1.  Discussed...

*Negative*
1.  Criticised...

Pre-emptives are pos X, neu Y, neg Z\
"""
```

- [ ] **Step 3: Sanity-check imports still resolve**

Run: `python -c "from autoso.pipeline.prompts import TEXTURE_FORMAT_INSTRUCTION, BUCKET_FORMAT_INSTRUCTION; print(len(TEXTURE_FORMAT_INSTRUCTION), len(BUCKET_FORMAT_INSTRUCTION))"`
Expected: two integers printed, no error.

- [ ] **Step 4: Commit**

```bash
git add autoso/pipeline/prompts.py
git commit -m "feat(prompts): drop no-citation rule; add multi-source hint"
```

---

## Task 9: Shared analysis types

**Files:**
- Create: `autoso/pipeline/analysis.py`

- [ ] **Step 1: Create module**

Create `autoso/pipeline/analysis.py`:

```python
# autoso/pipeline/analysis.py
"""Shared types for the two analysis modules (prompt / rag)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CitationRecord:
    citation_number: int    # 1-based, global across the pool
    text: str               # the comment's own text (no thread prepend)
    comment_id: str         # original Comment.id from the scrape
    position: int           # original flat position inside its post's flatten pass
    source_index: int       # which URL (0-indexed input order)


@dataclass
class AnalysisResult:
    output_cited: str                          # raw model output with [N] markers
    output_clean: str                          # markers stripped for Telegram
    citations: list[CitationRecord] = field(default_factory=list)
```

- [ ] **Step 2: Sanity check**

Run: `python -c "from autoso.pipeline.analysis import CitationRecord, AnalysisResult; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add autoso/pipeline/analysis.py
git commit -m "feat(pipeline): add shared AnalysisResult/CitationRecord"
```

---

## Task 10: citation.py — drop CitationNode/extract_citations; add citation_chunk_size kwarg

**Files:**
- Modify: `autoso/pipeline/citation.py`
- Modify: `tests/test_pipeline/test_citation.py`
- Modify: `tests/test_bot/test_handlers.py` (drop unused import)

- [ ] **Step 1: Inspect current citation test file**

Run: `cat tests/test_pipeline/test_citation.py`

Note which tests reference `CitationNode` or `extract_citations`. They must be deleted. Tests referencing only `strip_citation_markers` or `build_citation_engine` stay.

- [ ] **Step 2: Rewrite citation.py**

Replace `autoso/pipeline/citation.py` with:

```python
# autoso/pipeline/citation.py
import re

from llama_index.core import VectorStoreIndex
from llama_index.core.query_engine import CitationQueryEngine


def build_citation_engine(
    index: VectorStoreIndex,
    similarity_top_k: int = 10,
    system_prompt: str | None = None,
    citation_chunk_size: int = 512,
) -> CitationQueryEngine:
    """Build a CitationQueryEngine that annotates its response with [N] markers.

    `citation_chunk_size` controls how the engine splits documents into citable
    chunks. For flat-comment indexing (Phase 1Y RAG mode) a large value like
    4096 keeps each comment in a single chunk so citation numbers map 1:1 to
    comments instead of splitting one comment across multiple [N] markers.
    """
    kwargs: dict = {
        "similarity_top_k": similarity_top_k,
        "citation_chunk_size": citation_chunk_size,
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


def strip_citation_markers(text: str) -> str:
    """Remove all [N] citation markers from text."""
    return re.sub(r"\s*\[\d+\]", "", text).strip()
```

- [ ] **Step 3: Remove now-broken tests in test_citation.py**

Open `tests/test_pipeline/test_citation.py`. Delete every test function that references `CitationNode` or `extract_citations`. Also delete those names from the `from autoso.pipeline.citation import ...` line at the top. Keep tests for `strip_citation_markers` and `build_citation_engine`.

- [ ] **Step 4: Remove CitationNode import from bot test**

Edit `tests/test_bot/test_handlers.py`. Delete the line:

```python
from autoso.pipeline.citation import CitationNode
```

(The symbol is imported but not used in any remaining test assertions — verify with grep first.)

Run: `grep -n "CitationNode" tests/test_bot/test_handlers.py`
Expected after edit: no matches.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_pipeline/test_citation.py tests/test_bot/test_handlers.py -v`
Expected: all remaining tests pass. `ImportError` from deleted symbols is the failure signal if a reference was missed.

- [ ] **Step 6: Commit**

```bash
git add autoso/pipeline/citation.py tests/test_pipeline/test_citation.py tests/test_bot/test_handlers.py
git commit -m "refactor(citation): drop CitationNode/extract_citations; expose citation_chunk_size"
```

---

## Task 11: Prompt analysis — rendering helpers

**Files:**
- Create: `autoso/pipeline/prompt_analysis.py` (partial — helpers only)
- Test: `tests/test_pipeline/test_prompt_analysis.py`

- [ ] **Step 1: Write failing tests for rendering**

Create `tests/test_pipeline/test_prompt_analysis.py`:

```python
from autoso.pipeline.flatten import FlatComment
from autoso.pipeline.pool import Pool, PoolItem
from autoso.pipeline.prompt_analysis import render_flat_comment, render_user_message
from autoso.scraping.models import Post


def _post(url: str, platform: str = "facebook", content: str = "the post body") -> Post:
    return Post(
        id=url, platform=platform, url=url,
        page_title="", post_title="", date=None, author=None,
        content=content, likes=None, comments=[],
    )


def test_render_flat_comment_top_level():
    item = PoolItem(
        citation_number=5,
        flat=FlatComment(
            original_id="c1", position=0, text="alpha",
            thread_context=[], source_index=0,
        ),
    )

    rendered = render_flat_comment(item)

    assert rendered == "[5] alpha"


def test_render_flat_comment_reply_includes_thread():
    item = PoolItem(
        citation_number=12,
        flat=FlatComment(
            original_id="r1", position=4, text="disagreed",
            thread_context=["parent says", "first reply"], source_index=1,
        ),
    )

    rendered = render_flat_comment(item)

    assert rendered.startswith("[12] ↳ reply in thread:")
    assert "parent: parent says" in rendered
    assert "· first reply" in rendered
    assert rendered.endswith("disagreed")


def test_render_user_message_includes_sources_and_comments():
    posts = [_post("https://a.com", content="post A body"),
             _post("https://b.com", content="post B body")]
    pool = Pool(
        items=[
            PoolItem(1, FlatComment("a1", 0, "alpha", [], 0)),
            PoolItem(2, FlatComment("b1", 0, "bravo", [], 1)),
        ],
        posts=posts,
    )

    msg = render_user_message(
        pool=pool, format_instruction="Format TITLE", hg_block=None,
    )

    assert "POSTS (2 sources)" in msg
    assert "[Source 1 — FACEBOOK] https://a.com" in msg
    assert "post A body" in msg
    assert "[Source 2 — FACEBOOK] https://b.com" in msg
    assert "COMMENTS:" in msg
    assert "[1] alpha" in msg
    assert "[2] bravo" in msg
    assert "Format TITLE" in msg
    assert "After each bullet, append the citation markers" in msg


def test_render_user_message_with_hg_block():
    pool = Pool(items=[], posts=[_post("https://a.com")])

    msg = render_user_message(
        pool=pool, format_instruction="F", hg_block="BUCKET_LABELS_HERE",
    )

    assert "BUCKET HOLY GRAIL REFERENCE:" in msg
    assert "BUCKET_LABELS_HERE" in msg
    # HG block must appear before COMMENTS block
    assert msg.index("BUCKET HOLY GRAIL REFERENCE:") < msg.index("COMMENTS:")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pipeline/test_prompt_analysis.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement helpers**

Create `autoso/pipeline/prompt_analysis.py` with just the helpers for now:

```python
# autoso/pipeline/prompt_analysis.py
"""Prompt-mode analysis: direct Anthropic SDK with all comments inline."""
from __future__ import annotations

from typing import Optional

from autoso.pipeline.pool import Pool, PoolItem


_APPEND_INSTRUCTION = (
    "After each bullet, append the citation markers [N] for the comments that support it. "
    "Use the bracketed numbers shown in the COMMENTS block above."
)


def render_flat_comment(item: PoolItem) -> str:
    """Render a single PoolItem for the prompt's COMMENTS block."""
    n = item.citation_number
    flat = item.flat
    if not flat.thread_context:
        return f"[{n}] {flat.text}"
    lines = [f"[{n}] ↳ reply in thread:"]
    lines.append(f"  parent: {flat.thread_context[0]}")
    for prior in flat.thread_context[1:]:
        lines.append(f"  · {prior}")
    lines.append(flat.text)
    return "\n".join(lines)


def render_user_message(
    pool: Pool, format_instruction: str, hg_block: Optional[str] = None,
) -> str:
    """Assemble the single user-turn message for the Anthropic call."""
    parts: list[str] = []
    n_sources = len(pool.posts)
    parts.append(f"POSTS ({n_sources} sources):")
    for i, post in enumerate(pool.posts, start=1):
        parts.append(
            f"\n[Source {i} — {post.platform.upper()}] {post.url}\n{post.content or ''}"
        )
    if hg_block:
        parts.append(f"\nBUCKET HOLY GRAIL REFERENCE:\n{hg_block}")
    parts.append("\nCOMMENTS:")
    for item in pool.items:
        parts.append(render_flat_comment(item))
    parts.append("")
    parts.append(format_instruction)
    parts.append("")
    parts.append(_APPEND_INSTRUCTION)
    return "\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pipeline/test_prompt_analysis.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add autoso/pipeline/prompt_analysis.py tests/test_pipeline/test_prompt_analysis.py
git commit -m "feat(pipeline): prompt analysis rendering helpers"
```

---

## Task 12: Prompt analysis — citation extraction from model output

**Files:**
- Modify: `autoso/pipeline/prompt_analysis.py`
- Modify: `tests/test_pipeline/test_prompt_analysis.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_pipeline/test_prompt_analysis.py`:

```python
from autoso.pipeline.analysis import CitationRecord
from autoso.pipeline.prompt_analysis import extract_citations_from_output


def _pool_with_two_items() -> Pool:
    return Pool(
        items=[
            PoolItem(1, FlatComment("a1", 0, "alpha", [], 0)),
            PoolItem(2, FlatComment("b1", 0, "bravo", [], 1)),
        ],
        posts=[_post("https://a.com"), _post("https://b.com")],
    )


def test_extract_citations_returns_records_for_cited_markers():
    pool = _pool_with_two_items()
    output = "- 50% discussed alpha [1]\n- 50% discussed bravo [2]"

    records = extract_citations_from_output(output, pool)

    assert len(records) == 2
    assert records[0] == CitationRecord(
        citation_number=1, text="alpha", comment_id="a1", position=0, source_index=0,
    )
    assert records[1] == CitationRecord(
        citation_number=2, text="bravo", comment_id="b1", position=0, source_index=1,
    )


def test_extract_citations_deduplicates_repeated_markers():
    pool = _pool_with_two_items()
    output = "- thing [1][2]\n- other thing [1]"

    records = extract_citations_from_output(output, pool)

    assert len(records) == 2
    assert sorted(r.citation_number for r in records) == [1, 2]


def test_extract_citations_ignores_unknown_markers():
    pool = _pool_with_two_items()
    output = "- alpha [1] and some [99] bogus"

    records = extract_citations_from_output(output, pool)

    assert [r.citation_number for r in records] == [1]


def test_extract_citations_empty_when_no_markers():
    pool = _pool_with_two_items()
    output = "no markers here"

    assert extract_citations_from_output(output, pool) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pipeline/test_prompt_analysis.py -v`
Expected: 4 new tests FAIL with `ImportError: extract_citations_from_output`.

- [ ] **Step 3: Implement extractor**

Append to `autoso/pipeline/prompt_analysis.py`:

```python
import re

from autoso.pipeline.analysis import CitationRecord


_MARKER_RE = re.compile(r"\[(\d+)\]")


def extract_citations_from_output(
    output_text: str, pool: Pool
) -> list[CitationRecord]:
    """Pull [N] markers from model output and map to CitationRecords via the pool."""
    seen: set[int] = set()
    records: list[CitationRecord] = []
    for match in _MARKER_RE.finditer(output_text):
        n = int(match.group(1))
        if n in seen:
            continue
        seen.add(n)
        item = pool.lookup(n)
        if item is None:
            continue
        flat = item.flat
        records.append(
            CitationRecord(
                citation_number=n,
                text=flat.text,
                comment_id=flat.original_id,
                position=flat.position,
                source_index=flat.source_index,
            )
        )
    return records
```

Add the `import re` and `from autoso.pipeline.analysis import CitationRecord` to the top of the file (consolidate imports — don't leave them inline).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pipeline/test_prompt_analysis.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add autoso/pipeline/prompt_analysis.py tests/test_pipeline/test_prompt_analysis.py
git commit -m "feat(pipeline): extract [N] citations from prompt-mode output"
```

---

## Task 13: Prompt analysis — `run_prompt_analysis` top-level function

**Files:**
- Modify: `autoso/pipeline/prompt_analysis.py`
- Modify: `tests/test_pipeline/test_prompt_analysis.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_pipeline/test_prompt_analysis.py`:

```python
from unittest.mock import MagicMock, patch

from autoso.pipeline.analysis import AnalysisResult
from autoso.pipeline.prompt_analysis import run_prompt_analysis


def _texture_pool() -> Pool:
    return Pool(
        items=[
            PoolItem(1, FlatComment("a1", 0, "alpha", [], 0)),
            PoolItem(2, FlatComment("b1", 0, "bravo", [], 0)),
        ],
        posts=[_post("https://a.com")],
    )


def test_run_prompt_analysis_returns_result():
    pool = _texture_pool()

    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="- 100% said alpha [1]")]

    with patch("autoso.pipeline.prompt_analysis.anthropic.Anthropic") as MockClient, \
         patch("autoso.pipeline.prompt_analysis.config") as MockConfig:
        MockConfig.ANTHROPIC_API_KEY = "sk-test"
        MockConfig.CLAUDE_MODEL = "claude-sonnet-4-6"
        MockConfig.USE_OLLAMA = False
        MockClient.return_value.messages.create.return_value = fake_response

        result = run_prompt_analysis(
            mode="texture", title="My Title", pool=pool, hg_block=None,
        )

    assert isinstance(result, AnalysisResult)
    assert result.output_cited == "- 100% said alpha [1]"
    assert result.output_clean == "- 100% said alpha"
    assert [r.citation_number for r in result.citations] == [1]

    # Verify the SDK call shape
    call_kwargs = MockClient.return_value.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-4-6"
    assert call_kwargs["system"].startswith("This GPT's role")
    assert call_kwargs["messages"][0]["role"] == "user"
    assert "My Title" in call_kwargs["messages"][0]["content"]
    assert "[1] alpha" in call_kwargs["messages"][0]["content"]


def test_run_prompt_analysis_bucket_mode_includes_hg_block():
    pool = _texture_pool()

    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="*Positive*\n1.  praised [1]")]

    with patch("autoso.pipeline.prompt_analysis.anthropic.Anthropic") as MockClient, \
         patch("autoso.pipeline.prompt_analysis.config") as MockConfig:
        MockConfig.ANTHROPIC_API_KEY = "sk-test"
        MockConfig.CLAUDE_MODEL = "claude-sonnet-4-6"
        MockConfig.USE_OLLAMA = False
        MockClient.return_value.messages.create.return_value = fake_response

        run_prompt_analysis(
            mode="bucket", title="T", pool=pool, hg_block="BUCKET_LABELS",
        )

    call_kwargs = MockClient.return_value.messages.create.call_args.kwargs
    assert "BUCKET HOLY GRAIL REFERENCE:" in call_kwargs["messages"][0]["content"]
    assert "BUCKET_LABELS" in call_kwargs["messages"][0]["content"]


def test_run_prompt_analysis_raises_if_ollama_enabled():
    pool = _texture_pool()
    with patch("autoso.pipeline.prompt_analysis.config") as MockConfig:
        MockConfig.USE_OLLAMA = True
        try:
            run_prompt_analysis(
                mode="texture", title="T", pool=pool, hg_block=None,
            )
        except RuntimeError as e:
            assert "prompt mode" in str(e).lower()
        else:
            raise AssertionError("expected RuntimeError")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pipeline/test_prompt_analysis.py -v`
Expected: 3 new tests FAIL.

- [ ] **Step 3: Implement `run_prompt_analysis`**

Append to `autoso/pipeline/prompt_analysis.py`:

```python
import anthropic

import autoso.config as config
from autoso.pipeline.citation import strip_citation_markers
from autoso.pipeline.prompts import (
    BUCKET_FORMAT_INSTRUCTION,
    BUCKET_SYSTEM_PROMPT,
    TEXTURE_FORMAT_INSTRUCTION,
    TEXTURE_SYSTEM_PROMPT,
)
from autoso.pipeline.analysis import AnalysisResult


def run_prompt_analysis(
    mode: str,
    title: str,
    pool: Pool,
    hg_block: Optional[str],
) -> AnalysisResult:
    if getattr(config, "USE_OLLAMA", False):
        raise RuntimeError(
            "prompt mode requires Anthropic API; set USE_OLLAMA=false or use -m rag"
        )
    if mode == "texture":
        system = TEXTURE_SYSTEM_PROMPT
        format_instruction = TEXTURE_FORMAT_INSTRUCTION.format(title=title)
    elif mode == "bucket":
        system = BUCKET_SYSTEM_PROMPT
        format_instruction = BUCKET_FORMAT_INSTRUCTION.format(title=title)
    else:
        raise ValueError(f"unknown mode: {mode!r}")

    user_message = render_user_message(
        pool=pool, format_instruction=format_instruction, hg_block=hg_block,
    )

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )
    output_cited = "".join(block.text for block in response.content)
    output_clean = strip_citation_markers(output_cited)
    citations = extract_citations_from_output(output_cited, pool)
    return AnalysisResult(
        output_cited=output_cited,
        output_clean=output_clean,
        citations=citations,
    )
```

Move `import re`, `import anthropic`, `import autoso.config as config`, and the other imports to the top of the file (single import block).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pipeline/test_prompt_analysis.py -v`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add autoso/pipeline/prompt_analysis.py tests/test_pipeline/test_prompt_analysis.py
git commit -m "feat(pipeline): run_prompt_analysis end-to-end"
```

---

## Task 14: RAG analysis — index flat pool items

**Files:**
- Create: `autoso/pipeline/rag_analysis.py` (partial)
- Test: `tests/test_pipeline/test_rag_analysis.py`

- [ ] **Step 1: Write failing test for indexing**

Create `tests/test_pipeline/test_rag_analysis.py`:

```python
from unittest.mock import patch

from autoso.pipeline.flatten import FlatComment
from autoso.pipeline.pool import Pool, PoolItem
from autoso.pipeline.rag_analysis import _pool_documents
from autoso.scraping.models import Post


def _post(url: str) -> Post:
    return Post(
        id=url, platform="facebook", url=url,
        page_title="", post_title="", date=None, author=None,
        content="", likes=None, comments=[],
    )


def test_pool_documents_have_rendered_text_and_metadata():
    pool = Pool(
        items=[
            PoolItem(1, FlatComment("a1", 0, "alpha", [], 0)),
            PoolItem(2, FlatComment("r1", 1, "reply", ["parent text"], 1)),
        ],
        posts=[_post("https://a.com"), _post("https://b.com")],
    )

    docs = _pool_documents(pool)

    assert len(docs) == 2
    # Top-level rendering
    assert docs[0].text == "[1] alpha"
    assert docs[0].metadata == {
        "comment_id": "a1",
        "position": 0,
        "source_index": 0,
        "citation_number": 1,
    }
    # Reply rendering includes the thread
    assert "↳ reply in thread" in docs[1].text
    assert "parent text" in docs[1].text
    assert docs[1].text.endswith("reply")
    assert docs[1].metadata["source_index"] == 1
    assert docs[1].metadata["citation_number"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline/test_rag_analysis.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `_pool_documents`**

Create `autoso/pipeline/rag_analysis.py`:

```python
# autoso/pipeline/rag_analysis.py
"""RAG-mode analysis: index the flat pool and use CitationQueryEngine."""
from __future__ import annotations

import uuid
from typing import Optional

import chromadb
from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.vector_stores.chroma import ChromaVectorStore

from autoso.pipeline.analysis import AnalysisResult, CitationRecord
from autoso.pipeline.citation import build_citation_engine, strip_citation_markers
from autoso.pipeline.pool import Pool
from autoso.pipeline.prompt_analysis import render_flat_comment, render_user_message
from autoso.pipeline.prompts import (
    BUCKET_FORMAT_INSTRUCTION,
    BUCKET_SYSTEM_PROMPT,
    TEXTURE_FORMAT_INSTRUCTION,
    TEXTURE_SYSTEM_PROMPT,
)


def _pool_documents(pool: Pool) -> list[Document]:
    docs: list[Document] = []
    for item in pool.items:
        docs.append(
            Document(
                text=render_flat_comment(item),
                metadata={
                    "comment_id": item.flat.original_id,
                    "position": item.flat.position,
                    "source_index": item.flat.source_index,
                    "citation_number": item.citation_number,
                },
                doc_id=f"{item.flat.original_id}:{item.citation_number}",
            )
        )
    return docs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pipeline/test_rag_analysis.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add autoso/pipeline/rag_analysis.py tests/test_pipeline/test_rag_analysis.py
git commit -m "feat(pipeline): _pool_documents for RAG indexing"
```

---

## Task 15: RAG analysis — `run_rag_analysis` with source node mapping

**Files:**
- Modify: `autoso/pipeline/rag_analysis.py`
- Modify: `tests/test_pipeline/test_rag_analysis.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_pipeline/test_rag_analysis.py`:

```python
from unittest.mock import MagicMock

from autoso.pipeline.analysis import AnalysisResult, CitationRecord
from autoso.pipeline.rag_analysis import run_rag_analysis


def _pool_two_sources() -> Pool:
    return Pool(
        items=[
            PoolItem(1, FlatComment("a1", 0, "alpha", [], 0)),
            PoolItem(2, FlatComment("b1", 0, "bravo", [], 1)),
            PoolItem(3, FlatComment("b2", 1, "charlie", [], 1)),
        ],
        posts=[_post("https://a.com"), _post("https://b.com")],
    )


def _source_node(comment_id: str, citation_number: int, source_index: int, position: int, text: str):
    node = MagicMock()
    node.node.text = text
    node.node.metadata = {
        "comment_id": comment_id,
        "citation_number": citation_number,
        "source_index": source_index,
        "position": position,
    }
    return node


def test_run_rag_analysis_returns_result_with_citations():
    pool = _pool_two_sources()

    fake_response = MagicMock()
    fake_response.__str__ = lambda self: "- bullet [1]\n- bullet [2]"
    fake_response.source_nodes = [
        _source_node("a1", 1, 0, 0, "[1] alpha"),
        _source_node("b1", 2, 1, 0, "[2] bravo"),
    ]

    fake_engine = MagicMock()
    fake_engine.query.return_value = fake_response

    with patch("autoso.pipeline.rag_analysis.build_citation_engine", return_value=fake_engine), \
         patch("autoso.pipeline.rag_analysis.VectorStoreIndex.from_documents", return_value=MagicMock()), \
         patch("autoso.pipeline.rag_analysis.chromadb.EphemeralClient"):
        result = run_rag_analysis(
            mode="texture", title="T", pool=pool, hg_block=None,
        )

    assert isinstance(result, AnalysisResult)
    assert result.output_cited == "- bullet [1]\n- bullet [2]"
    assert result.output_clean == "- bullet\n- bullet"
    citation_numbers = sorted(r.citation_number for r in result.citations)
    assert citation_numbers == [1, 2]


def test_run_rag_analysis_dedupes_by_comment_id_and_source():
    """Two source nodes sharing comment_id+source_index produce one citation."""
    pool = _pool_two_sources()
    fake_response = MagicMock()
    fake_response.__str__ = lambda self: "- bullet [1]"
    fake_response.source_nodes = [
        _source_node("a1", 1, 0, 0, "[1] alpha part 1"),
        _source_node("a1", 1, 0, 0, "[1] alpha part 2"),
    ]
    fake_engine = MagicMock()
    fake_engine.query.return_value = fake_response

    with patch("autoso.pipeline.rag_analysis.build_citation_engine", return_value=fake_engine), \
         patch("autoso.pipeline.rag_analysis.VectorStoreIndex.from_documents", return_value=MagicMock()), \
         patch("autoso.pipeline.rag_analysis.chromadb.EphemeralClient"):
        result = run_rag_analysis(
            mode="texture", title="T", pool=pool, hg_block=None,
        )

    assert len(result.citations) == 1


def test_run_rag_analysis_passes_similarity_top_k_equal_to_pool_size():
    pool = _pool_two_sources()
    fake_response = MagicMock()
    fake_response.__str__ = lambda self: "x"
    fake_response.source_nodes = []
    fake_engine = MagicMock()
    fake_engine.query.return_value = fake_response

    with patch("autoso.pipeline.rag_analysis.build_citation_engine", return_value=fake_engine) as mock_build, \
         patch("autoso.pipeline.rag_analysis.VectorStoreIndex.from_documents", return_value=MagicMock()), \
         patch("autoso.pipeline.rag_analysis.chromadb.EphemeralClient"):
        run_rag_analysis(mode="texture", title="T", pool=pool, hg_block=None)

    _, kwargs = mock_build.call_args
    assert kwargs["similarity_top_k"] == 3
    assert kwargs["citation_chunk_size"] == 4096
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pipeline/test_rag_analysis.py -v`
Expected: 3 new tests FAIL.

- [ ] **Step 3: Implement `run_rag_analysis`**

Append to `autoso/pipeline/rag_analysis.py`:

```python
def _index_pool(pool: Pool) -> VectorStoreIndex:
    client = chromadb.EphemeralClient()
    collection = client.create_collection(f"rag_{uuid.uuid4().hex[:12]}")
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage = StorageContext.from_defaults(vector_store=vector_store)
    return VectorStoreIndex.from_documents(
        _pool_documents(pool), storage_context=storage, show_progress=False,
    )


def _extract_rag_citations(response, pool: Pool) -> list[CitationRecord]:
    seen: set[tuple[str, int]] = set()
    records: list[CitationRecord] = []
    for node in response.source_nodes:
        meta = node.node.metadata
        comment_id = meta.get("comment_id")
        source_index = meta.get("source_index", 0)
        key = (comment_id, source_index)
        if key in seen:
            continue
        seen.add(key)
        citation_number = meta.get("citation_number")
        item = pool.lookup(citation_number) if citation_number else None
        # Prefer the pool's authoritative text over the indexed (rendered) chunk
        text = item.flat.text if item else node.node.text
        position = item.flat.position if item else meta.get("position", -1)
        records.append(
            CitationRecord(
                citation_number=citation_number,
                text=text,
                comment_id=comment_id,
                position=position,
                source_index=source_index,
            )
        )
    return records


def run_rag_analysis(
    mode: str,
    title: str,
    pool: Pool,
    hg_block: Optional[str],
) -> AnalysisResult:
    if mode == "texture":
        system = TEXTURE_SYSTEM_PROMPT
        format_instruction = TEXTURE_FORMAT_INSTRUCTION.format(title=title)
    elif mode == "bucket":
        system = BUCKET_SYSTEM_PROMPT
        format_instruction = BUCKET_FORMAT_INSTRUCTION.format(title=title)
    else:
        raise ValueError(f"unknown mode: {mode!r}")

    index = _index_pool(pool)
    engine = build_citation_engine(
        index,
        similarity_top_k=max(len(pool.items), 1),
        system_prompt=system,
        citation_chunk_size=4096,
    )

    # For RAG mode, omit the "append [N]" instruction — CitationQueryEngine handles it.
    query = render_user_message(
        pool=Pool(items=[], posts=pool.posts),  # posts only; comments come from the index
        format_instruction=format_instruction,
        hg_block=hg_block,
    )

    response = engine.query(query)
    output_cited = str(response)
    output_clean = strip_citation_markers(output_cited)
    citations = _extract_rag_citations(response, pool)
    return AnalysisResult(
        output_cited=output_cited,
        output_clean=output_clean,
        citations=citations,
    )
```

Note: the `render_user_message` call here passes an empty-items `Pool` so the COMMENTS block in the query text is empty — the index is the source of comments for RAG. The `_APPEND_INSTRUCTION` tail is still appended, which is harmless but mildly redundant for RAG; leave it — CitationQueryEngine's template ignores instructions it doesn't need, and the cost is ≈ one sentence of tokens.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pipeline/test_rag_analysis.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add autoso/pipeline/rag_analysis.py tests/test_pipeline/test_rag_analysis.py
git commit -m "feat(pipeline): run_rag_analysis with per-comment citation mapping"
```

---

## Task 16: Storage — `store_multi_result`

**Files:**
- Modify: `autoso/storage/supabase.py`
- Create: `tests/test_storage/__init__.py`
- Create: `tests/test_storage/test_supabase_multi.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_storage/__init__.py` (empty file).

Create `tests/test_storage/test_supabase_multi.py`:

```python
from unittest.mock import MagicMock, patch

from autoso.pipeline.analysis import AnalysisResult, CitationRecord
from autoso.storage.supabase import store_multi_result


def _fake_client():
    """A MagicMock supabase client whose table().insert().execute() returns .data rows."""
    client = MagicMock()

    # Per-table state for the .execute() returns
    def table(name):
        t = MagicMock()
        t._name = name
        def insert(rows):
            chain = MagicMock()
            # If inserting analysis_sources, return rows with stable ids
            if name == "analysis_sources":
                data = []
                for i, r in enumerate(rows if isinstance(rows, list) else [rows]):
                    data.append({**r, "id": f"src-{i}"})
                chain.execute.return_value = MagicMock(data=data)
            else:
                payload = rows if isinstance(rows, list) else [rows]
                chain.execute.return_value = MagicMock(data=payload)
            return chain
        t.insert = insert
        return t

    client.table = table
    return client


def test_store_multi_result_inserts_analysis_sources_and_citations():
    analysis = AnalysisResult(
        output_cited="- thing [1][2]",
        output_clean="- thing",
        citations=[
            CitationRecord(1, "alpha", "a1", 0, source_index=0),
            CitationRecord(2, "bravo", "b1", 0, source_index=1),
        ],
    )

    client = _fake_client()

    with patch("autoso.storage.supabase._get_client", return_value=client):
        run_id = store_multi_result(
            urls=["https://a.com", "https://b.com"],
            scrape_ids=["sid-a", "sid-b"],
            mode="texture",
            analysis_mode="prompt",
            title="My Title",
            analysis=analysis,
        )

    assert isinstance(run_id, str) and len(run_id) > 0


def test_store_multi_result_resolves_source_id_via_source_index():
    analysis = AnalysisResult(
        output_cited="[2]",
        output_clean="",
        citations=[CitationRecord(2, "bravo", "b1", 0, source_index=1)],
    )

    # Spy: capture every insert call with its table name and rows
    insert_log: list[tuple[str, list[dict]]] = []

    class SpyClient:
        def table(self, name):
            t = MagicMock()
            def insert(rows):
                chain = MagicMock()
                payload = rows if isinstance(rows, list) else [rows]
                insert_log.append((name, payload))
                if name == "analysis_sources":
                    chain.execute.return_value = MagicMock(
                        data=[{**r, "id": f"src-{i}"} for i, r in enumerate(payload)]
                    )
                else:
                    chain.execute.return_value = MagicMock(data=payload)
                return chain
            t.insert = insert
            return t

    with patch("autoso.storage.supabase._get_client", return_value=SpyClient()):
        store_multi_result(
            urls=["https://a.com", "https://b.com"],
            scrape_ids=["sid-a", "sid-b"],
            mode="texture",
            analysis_mode="prompt",
            title="T",
            analysis=analysis,
        )

    # Find the citations insert
    citation_inserts = [rows for name, rows in insert_log if name == "citations"]
    assert citation_inserts, "citations insert did not happen"
    citation_row = citation_inserts[0][0]
    assert citation_row["citation_number"] == 2
    assert citation_row["comment_id"] == "b1"
    # source_index=1 → the second source row → id "src-1"
    assert citation_row["source_id"] == "src-1"

    # analyses row should carry analysis_mode + title + outputs, no 'url'
    analyses_inserts = [rows for name, rows in insert_log if name == "analyses"]
    assert analyses_inserts
    analysis_row = analyses_inserts[0][0]
    assert analysis_row["analysis_mode"] == "prompt"
    assert analysis_row["mode"] == "texture"
    assert analysis_row["title"] == "T"
    assert "url" not in analysis_row
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_storage/ -v`
Expected: FAIL with `ImportError: cannot import name 'store_multi_result'`.

- [ ] **Step 3: Replace `store_result` with `store_multi_result`**

Edit `autoso/storage/supabase.py`. Replace the existing `store_result` function with:

```python
from autoso.pipeline.analysis import AnalysisResult


def store_multi_result(
    urls: list[str],
    scrape_ids: list[str],
    mode: str,
    analysis_mode: str,
    title: str,
    analysis: AnalysisResult,
) -> str:
    """Insert analysis + sources + citations. Returns run_id."""
    if len(urls) != len(scrape_ids):
        raise ValueError("urls and scrape_ids must be the same length")

    client = _get_client()
    run_id = str(uuid.uuid4())

    client.table("analyses").insert(
        {
            "id": run_id,
            "mode": mode,
            "analysis_mode": analysis_mode,
            "title": title,
            "output": analysis.output_clean,
            "output_cited": analysis.output_cited,
        }
    ).execute()

    source_rows = [
        {
            "analysis_id": run_id,
            "url": url,
            "link_index": i,
            "scrape_id": scrape_ids[i],
        }
        for i, url in enumerate(urls)
    ]
    sources_resp = client.table("analysis_sources").insert(source_rows).execute()
    source_rows_returned = sources_resp.data or []
    # Build source_index -> source_id map using link_index we just inserted.
    source_id_by_index: dict[int, str] = {}
    for row in source_rows_returned:
        source_id_by_index[row["link_index"]] = row["id"]

    if analysis.citations:
        citation_rows = [
            {
                "run_id": run_id,
                "source_id": source_id_by_index.get(c.source_index),
                "citation_number": c.citation_number,
                "text": c.text,
                "comment_id": c.comment_id,
                "position": c.position,
            }
            for c in analysis.citations
        ]
        client.table("citations").insert(citation_rows).execute()

    return run_id
```

Leave `store_scrape` and `get_recent_scrape` untouched. **Delete** the old `store_result` function entirely — it has no callers after Task 17.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_storage/ -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add autoso/storage/supabase.py tests/test_storage/__init__.py tests/test_storage/test_supabase_multi.py
git commit -m "feat(storage): store_multi_result with analysis_sources junction"
```

---

## Task 17: Pipeline orchestration rewrite

**Files:**
- Modify: `autoso/pipeline/pipeline.py`
- Modify: `tests/test_pipeline/test_pipeline.py`

- [ ] **Step 1: Rewrite `pipeline.py`**

Replace `autoso/pipeline/pipeline.py` entirely with:

```python
# autoso/pipeline/pipeline.py
import logging
from dataclasses import dataclass, field
from typing import List, Literal, Optional

from autoso.pipeline.analysis import AnalysisResult, CitationRecord
from autoso.pipeline.citation import build_citation_engine
from autoso.pipeline.flatten import flatten_post_comments
from autoso.pipeline.holy_grail import load_holy_grail
from autoso.pipeline.llm import configure_llm
from autoso.pipeline.pool import Pool, build_pool
from autoso.pipeline.prompt_analysis import run_prompt_analysis
from autoso.pipeline.rag_analysis import run_rag_analysis
from autoso.pipeline.scaling import comments_per_link
from autoso.pipeline.title import infer_title
from autoso.scraping import scrape
from autoso.storage.supabase import store_multi_result

logger = logging.getLogger(__name__)

Mode = Literal["texture", "bucket"]
AnalysisMode = Literal["prompt", "rag"]


@dataclass
class PipelineResult:
    title: str
    output: str
    output_cited: str
    citations: List[CitationRecord] = field(default_factory=list)
    run_id: str = ""


def _run_holy_grail() -> str:
    holy_grail_index = load_holy_grail()
    hg_engine = build_citation_engine(holy_grail_index, similarity_top_k=20)
    hg_response = hg_engine.query(
        "List all bucket labels for MINDEF/SAF/NS/Defence sentiment analysis"
    )
    return str(hg_response)


def run_pipeline(
    urls: list[str],
    mode: Mode,
    analysis_mode: AnalysisMode = "prompt",
    provided_title: Optional[str] = None,
) -> PipelineResult:
    if not urls:
        raise ValueError("run_pipeline requires at least one URL")

    configure_llm()

    # 1. Scrape — Phase 1X cache absorbs repeats; sequential for scraper safety.
    sources = [scrape(url) for url in urls]
    scrape_ids = [sid for sid, _ in sources]
    posts = [post for _, post in sources]
    for url, post in zip(urls, posts):
        logger.info(
            "Scraped %d comments from %s (%s)", len(post.comments), post.platform, url,
        )

    # 2. Flatten with scaling.
    n_cap = comments_per_link(len(urls))
    flattened = [
        flatten_post_comments(post, n_cap, i)
        for i, post in enumerate(posts)
    ]
    total = sum(len(fl) for fl in flattened)
    if total == 0:
        raise RuntimeError(
            "No comments retrieved from any URL. Check scraper credentials/session."
        )
    logger.info("Pool size: %d comments across %d sources", total, len(urls))

    # 3. Pool.
    pool = build_pool(flattened, posts)

    # 4. Title (first post wins).
    title = provided_title or infer_title(posts[0])

    # 5. Holy Grail (bucket only, shared across analysis modes).
    hg_block: Optional[str] = None
    if mode == "bucket":
        hg_block = _run_holy_grail()

    # 6. Analyse.
    if analysis_mode == "prompt":
        analysis: AnalysisResult = run_prompt_analysis(
            mode=mode, title=title, pool=pool, hg_block=hg_block,
        )
    else:
        analysis = run_rag_analysis(
            mode=mode, title=title, pool=pool, hg_block=hg_block,
        )

    # 7. Persist.
    run_id = store_multi_result(
        urls=urls,
        scrape_ids=scrape_ids,
        mode=mode,
        analysis_mode=analysis_mode,
        title=title,
        analysis=analysis,
    )

    return PipelineResult(
        title=title,
        output=analysis.output_clean,
        output_cited=analysis.output_cited,
        citations=analysis.citations,
        run_id=run_id,
    )
```

- [ ] **Step 2: Rewrite `test_pipeline.py`**

Replace `tests/test_pipeline/test_pipeline.py` entirely with:

```python
import re
from unittest.mock import MagicMock, patch

from autoso.pipeline.analysis import AnalysisResult, CitationRecord
from autoso.pipeline.pipeline import PipelineResult, run_pipeline
from autoso.scraping.models import Comment, Post


def _make_post(platform: str = "reddit", url: str = "https://reddit.com/test") -> Post:
    return Post(
        id="p1", platform=platform, url=url,
        page_title=f"{platform} page", post_title="XLS25 Concludes",
        date=None, author=None,
        content="The annual exercise has ended.", likes=None,
        comments=[
            Comment(id="c1", platform=platform, author=None, date=None,
                    text="SAF soldiers were impressive", likes=None, position=0),
            Comment(id="c2", platform=platform, author=None, date=None,
                    text="Good for SG-US bilateral relations", likes=None, position=1),
            Comment(id="c3", platform=platform, author=None, date=None,
                    text="NS builds character and resilience", likes=None, position=2),
        ],
    )


def _fake_analysis_result(mode: str) -> AnalysisResult:
    cited = (
        "- 60% praised SAF [1]\n- 40% discussed NS [2]"
        if mode == "texture"
        else "*Positive*\n1.  Praised SAF [1]\n*Neutral*\n1.  Discussed NS [2]\n*Negative*\n1.  Criticised [3]"
    )
    clean = re.sub(r"\s*\[\d+\]", "", cited).strip()
    return AnalysisResult(
        output_cited=cited,
        output_clean=clean,
        citations=[
            CitationRecord(1, "SAF soldiers were impressive", "c1", 0, 0),
            CitationRecord(2, "Good for SG-US bilateral relations", "c2", 1, 0),
        ],
    )


def _patches(mode: str, post: Post, *, run_id: str = "run-123"):
    return [
        patch("autoso.pipeline.pipeline.scrape", return_value=("sid-1", post)),
        patch("autoso.pipeline.pipeline.configure_llm"),
        patch("autoso.pipeline.pipeline.store_multi_result", return_value=run_id),
        patch("autoso.pipeline.pipeline.run_prompt_analysis", return_value=_fake_analysis_result(mode)),
        patch("autoso.pipeline.pipeline.run_rag_analysis", return_value=_fake_analysis_result(mode)),
        patch("autoso.pipeline.pipeline._run_holy_grail", return_value="HG"),
    ]


def test_texture_returns_pipeline_result_single_url():
    post = _make_post()
    patches = _patches("texture", post)
    for p in patches: p.start()
    try:
        result = run_pipeline(
            urls=["https://reddit.com/r/test/comments/abc"],
            mode="texture",
            analysis_mode="prompt",
            provided_title="XLS25 Concludes",
        )
        assert isinstance(result, PipelineResult)
        assert result.title == "XLS25 Concludes"
        assert result.run_id == "run-123"
        assert not re.search(r"\[\d+\]", result.output)
    finally:
        for p in patches: p.stop()


def test_texture_multi_url_passes_all_scrape_ids_to_storage():
    post = _make_post()
    patches = _patches("texture", post)
    for p in patches: p.start()
    try:
        run_pipeline(
            urls=["https://reddit.com/a", "https://reddit.com/b"],
            mode="texture",
            analysis_mode="prompt",
            provided_title="T",
        )
        store_mock = patches[2]
        _, kwargs = store_mock.call_args
        assert kwargs["urls"] == ["https://reddit.com/a", "https://reddit.com/b"]
        assert kwargs["scrape_ids"] == ["sid-1", "sid-1"]  # mocked scrape returns same id
        assert kwargs["analysis_mode"] == "prompt"
    finally:
        for p in patches: p.stop()


def test_rag_mode_dispatches_to_rag_analysis():
    post = _make_post()
    patches = _patches("texture", post)
    for p in patches: p.start()
    try:
        run_pipeline(
            urls=["https://reddit.com/a"],
            mode="texture",
            analysis_mode="rag",
            provided_title="T",
        )
        prompt_mock = patches[3]
        rag_mock = patches[4]
        prompt_mock.assert_not_called()
        rag_mock.assert_called_once()
    finally:
        for p in patches: p.stop()


def test_bucket_runs_holy_grail_before_analysis():
    post = _make_post()
    patches = _patches("bucket", post)
    for p in patches: p.start()
    try:
        run_pipeline(
            urls=["https://reddit.com/a"],
            mode="bucket",
            analysis_mode="prompt",
            provided_title="T",
        )
        hg_mock = patches[5]
        prompt_mock = patches[3]
        hg_mock.assert_called_once()
        _, kwargs = prompt_mock.call_args
        assert kwargs["hg_block"] == "HG"
    finally:
        for p in patches: p.stop()


def test_texture_skips_holy_grail():
    post = _make_post()
    patches = _patches("texture", post)
    for p in patches: p.start()
    try:
        run_pipeline(
            urls=["https://reddit.com/a"],
            mode="texture",
            analysis_mode="prompt",
            provided_title="T",
        )
        patches[5].assert_not_called()
    finally:
        for p in patches: p.stop()


def test_empty_urls_raises():
    try:
        run_pipeline(urls=[], mode="texture")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_title_inferred_when_not_provided():
    post = _make_post()
    patches = _patches("texture", post)
    extra = patch("autoso.pipeline.pipeline.infer_title", return_value="Inferred")
    for p in patches: p.start()
    extra.start()
    try:
        result = run_pipeline(
            urls=["https://reddit.com/a"],
            mode="texture",
            analysis_mode="prompt",
        )
        assert result.title == "Inferred"
    finally:
        for p in patches: p.stop()
        extra.stop()
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_pipeline/test_pipeline.py -v`
Expected: 7 passed.

- [ ] **Step 4: Run full pipeline test suite for regressions**

Run: `pytest tests/test_pipeline/ -v`
Expected: all tests pass (scaling, flatten, pool, prompt_analysis, rag_analysis, pipeline, citation, indexer, holy_grail, llm, title).

- [ ] **Step 5: Commit**

```bash
git add autoso/pipeline/pipeline.py tests/test_pipeline/test_pipeline.py
git commit -m "feat(pipeline): multi-URL run_pipeline with analysis_mode dispatch"
```

---

## Task 18: Bot — argument parser helper

**Files:**
- Modify: `autoso/bot/handlers.py`
- Modify: `tests/test_bot/test_handlers.py`

- [ ] **Step 1: Write failing parser tests**

Append to `tests/test_bot/test_handlers.py`:

```python
import pytest

from autoso.bot.handlers import ArgParseError, _parse_analysis_args


def test_parse_single_url_no_title_no_mode():
    urls, mode, title = _parse_analysis_args(["https://reddit.com/a"])
    assert urls == ["https://reddit.com/a"]
    assert mode == "prompt"
    assert title is None


def test_parse_multiple_urls():
    urls, _, _ = _parse_analysis_args([
        "https://reddit.com/a", "http://fb.com/b", "https://x.com/c",
    ])
    assert urls == ["https://reddit.com/a", "http://fb.com/b", "https://x.com/c"]


def test_parse_mode_flag_short():
    urls, mode, _ = _parse_analysis_args(["https://reddit.com/a", "-m", "rag"])
    assert urls == ["https://reddit.com/a"]
    assert mode == "rag"


def test_parse_mode_flag_long():
    _, mode, _ = _parse_analysis_args(["https://reddit.com/a", "--mode", "prompt"])
    assert mode == "prompt"


def test_parse_title_double_quotes_single_token():
    _, _, title = _parse_analysis_args(["https://reddit.com/a", '"My Title"'])
    assert title == "My Title"


def test_parse_title_double_quotes_spanning_multiple_tokens():
    _, _, title = _parse_analysis_args([
        "https://reddit.com/a", '"My', "Very", 'Long', 'Title"',
    ])
    assert title == "My Very Long Title"


def test_parse_title_single_quotes():
    _, _, title = _parse_analysis_args([
        "https://reddit.com/a", "'XLS25", "Concludes'",
    ])
    assert title == "XLS25 Concludes"


def test_parse_urls_mode_and_title():
    urls, mode, title = _parse_analysis_args([
        "https://reddit.com/a", "https://fb.com/b", "-m", "rag", '"Combined View"',
    ])
    assert urls == ["https://reddit.com/a", "https://fb.com/b"]
    assert mode == "rag"
    assert title == "Combined View"


def test_parse_rejects_empty():
    with pytest.raises(ArgParseError):
        _parse_analysis_args([])


def test_parse_rejects_no_urls():
    with pytest.raises(ArgParseError):
        _parse_analysis_args(["-m", "prompt", '"Title"'])


def test_parse_rejects_unknown_mode_value():
    with pytest.raises(ArgParseError):
        _parse_analysis_args(["https://reddit.com/a", "-m", "banana"])


def test_parse_rejects_mode_flag_without_value():
    with pytest.raises(ArgParseError):
        _parse_analysis_args(["https://reddit.com/a", "-m"])


def test_parse_rejects_unquoted_random_token():
    with pytest.raises(ArgParseError):
        _parse_analysis_args(["https://reddit.com/a", "stray_word"])


def test_parse_rejects_too_many_urls():
    with pytest.raises(ArgParseError):
        _parse_analysis_args([f"https://x.com/{i}" for i in range(51)])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_bot/test_handlers.py -v`
Expected: 13 new tests FAIL with `ImportError: ArgParseError`.

- [ ] **Step 3: Implement parser**

Edit `autoso/bot/handlers.py`. Add near the top (after the existing imports, before `_split_message`):

```python
MAX_URLS = 50
_VALID_MODES = {"prompt", "rag"}


class ArgParseError(ValueError):
    """Raised with a user-facing message when command argument parsing fails."""


def _parse_analysis_args(
    args: list[str],
) -> tuple[list[str], str, str | None]:
    """Parse /texture and /bucket arguments.

    Supported patterns (any order of tokens after URLs):
      /texture <url> [url ...] [-m|--mode prompt|rag] ["Title"|'Title']

    Rules:
      * At least 1 URL required; max {MAX_URLS}.
      * Mode defaults to 'prompt'. -m/--mode must be followed by prompt|rag.
      * A title token starts with " or ' and ends with the same quote.
        It may span multiple whitespace-split tokens — all intermediate
        tokens are joined with spaces until the closing quote is found.
      * Any arg that is neither a URL, a mode flag, nor part of a quoted
        title → ArgParseError.
    """
    if not args:
        raise ArgParseError("No arguments provided.")

    urls: list[str] = []
    mode: str = "prompt"
    title: str | None = None

    i = 0
    n = len(args)
    while i < n:
        tok = args[i]
        if tok.startswith("http://") or tok.startswith("https://"):
            urls.append(tok)
            i += 1
            continue
        if tok in ("-m", "--mode"):
            if i + 1 >= n:
                raise ArgParseError(f"{tok} requires a value (prompt|rag).")
            value = args[i + 1]
            if value not in _VALID_MODES:
                raise ArgParseError(
                    f"Unknown mode {value!r}. Use prompt or rag."
                )
            mode = value
            i += 2
            continue
        if tok.startswith('"') or tok.startswith("'"):
            quote = tok[0]
            parts = [tok.lstrip(quote)]
            # Did the quote close on the same token?
            if len(tok) >= 2 and tok.endswith(quote):
                title = tok[1:-1]
                i += 1
                continue
            i += 1
            closed = False
            while i < n:
                piece = args[i]
                if piece.endswith(quote):
                    parts.append(piece[:-1])
                    closed = True
                    i += 1
                    break
                parts.append(piece)
                i += 1
            if not closed:
                raise ArgParseError(f"Unterminated quoted title: {tok}")
            title = " ".join(parts).strip()
            continue
        raise ArgParseError(
            f"Unexpected token {tok!r}. "
            "Expected URL, -m/--mode, or a quoted title."
        )

    if not urls:
        raise ArgParseError("At least one URL (http:// or https://) required.")
    if len(urls) > MAX_URLS:
        raise ArgParseError(
            f"Too many URLs ({len(urls)}); the cap is {MAX_URLS}."
        )
    return urls, mode, title
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_bot/test_handlers.py -v`
Expected: all parser tests pass; handler tests still pass (we haven't changed `_handle_analysis` yet).

- [ ] **Step 5: Commit**

```bash
git add autoso/bot/handlers.py tests/test_bot/test_handlers.py
git commit -m "feat(bot): argument parser for multi-URL + mode flag + quoted title"
```

---

## Task 19: Bot — wire parser into `_handle_analysis` + update `/start`

**Files:**
- Modify: `autoso/bot/handlers.py`
- Modify: `tests/test_bot/test_handlers.py`

- [ ] **Step 1: Update failing handler tests**

In `tests/test_bot/test_handlers.py`, replace `test_texture_handler_calls_pipeline_and_replies`, `test_handler_notifies_user_when_output_too_long`, and `test_handler_replies_on_pipeline_exception` (they pass `run_pipeline` a single URL but we're changing it to a list) with:

```python
async def test_texture_handler_calls_pipeline_with_url_list():
    update, context = _make_update(99, ["https://reddit.com/r/sg/comments/abc"])
    mock_result = PipelineResult(
        title="Test", output="- 50% praised SAF",
        output_cited="- 50% praised SAF [1]", run_id="run-abc",
    )
    with patch("autoso.bot.handlers.run_pipeline", return_value=mock_result) as m:
        await texture_handler(update, context)

    _, kwargs = m.call_args
    assert kwargs["urls"] == ["https://reddit.com/r/sg/comments/abc"]
    assert kwargs["mode"] == "texture"
    assert kwargs["analysis_mode"] == "prompt"

    calls = [str(c) for c in update.message.reply_text.call_args_list]
    assert any("praised SAF" in c for c in calls)


async def test_texture_handler_multi_url_with_rag_mode():
    update, context = _make_update(99, [
        "https://reddit.com/a", "https://reddit.com/b", "--mode", "rag", '"My Title"',
    ])
    mock_result = PipelineResult(
        title="My Title", output="out", output_cited="out", run_id="r",
    )
    with patch("autoso.bot.handlers.run_pipeline", return_value=mock_result) as m:
        await texture_handler(update, context)

    _, kwargs = m.call_args
    assert kwargs["urls"] == ["https://reddit.com/a", "https://reddit.com/b"]
    assert kwargs["analysis_mode"] == "rag"
    assert kwargs["provided_title"] == "My Title"


async def test_handler_replies_with_parser_error_on_bad_args():
    update, context = _make_update(99, ["not_a_url"])
    await texture_handler(update, context)
    calls = [str(c) for c in update.message.reply_text.call_args_list]
    assert any("URL" in c or "expected" in c.lower() or "unexpected" in c.lower() for c in calls)


async def test_handler_notifies_user_when_output_too_long():
    update, context = _make_update(99, ["https://reddit.com/r/sg/comments/abc"])
    long_output = "x" * 5000
    mock_result = PipelineResult(
        title="Test", output=long_output, output_cited=long_output, run_id="run-abc",
    )
    with patch("autoso.bot.handlers.run_pipeline", return_value=mock_result):
        await texture_handler(update, context)

    calls = [str(c) for c in update.message.reply_text.call_args_list]
    assert any("too long" in c for c in calls) or any("5000" in c for c in calls)
    assert any("run-abc" in c for c in calls)


async def test_handler_replies_on_pipeline_exception():
    update, context = _make_update(99, ["https://reddit.com/r/sg/comments/abc"])
    with patch("autoso.bot.handlers.run_pipeline", side_effect=RuntimeError("scrape failed")):
        await texture_handler(update, context)
    calls = [str(c) for c in update.message.reply_text.call_args_list]
    assert any("error" in c.lower() for c in calls)
```

Also update `test_texture_handler_no_args_sends_usage` — it already covers the empty case; verify it still passes.

Update `test_start_handler_replies` to assert the new text:

```python
async def test_start_handler_replies():
    update, context = _make_update(99, [])
    await start_handler(update, context)
    text = update.message.reply_text.call_args.args[0]
    assert "/texture" in text
    assert "/bucket" in text
    assert "-m" in text or "--mode" in text
```

- [ ] **Step 2: Run tests to verify the updated ones fail**

Run: `pytest tests/test_bot/test_handlers.py -v`
Expected: updated tests FAIL because `_handle_analysis` still uses the old flow.

- [ ] **Step 3: Update `_handle_analysis`**

In `autoso/bot/handlers.py`, replace `_handle_analysis` with:

```python
async def _handle_analysis(
    update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str
):
    try:
        urls, analysis_mode, provided_title = _parse_analysis_args(
            context.args or []
        )
    except ArgParseError as e:
        await update.message.reply_text(
            f"{e}\n\nUsage: /{mode} <url> [url ...] [-m prompt|rag] [\"Title\"]"
        )
        return

    await update.message.reply_text(
        f"Processing {len(urls)} link(s) in {analysis_mode} mode — this may take a minute."
    )

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            _pipeline_executor,
            functools.partial(
                run_pipeline,
                urls=urls,
                mode=mode,
                analysis_mode=analysis_mode,
                provided_title=provided_title,
            ),
        )
        output = result.output

        if len(output) > TELEGRAM_MAX_LENGTH:
            await update.message.reply_text(
                "Output too long for one message "
                f"({len(output)} chars). "
                f"View full citations: {config.CITATION_UI_BASE_URL.rstrip('/')}/{result.run_id}"
            )

        chunks = _split_message(output)
        for chunk in chunks:
            try:
                await update.message.reply_text(chunk, parse_mode="Markdown")
            except BadRequest:
                logger.warning(
                    "Markdown parse failed for run_id=%s — sending plain text",
                    result.run_id,
                )
                await update.message.reply_text(chunk)

    except Exception:
        logger.exception("Pipeline error for urls=%s mode=%s", urls, mode)
        await update.message.reply_text(
            "An error occurred while processing your request. Check logs for details."
        )
```

- [ ] **Step 4: Update `/start` text**

In `autoso/bot/handlers.py`, replace the `start_handler` body:

```python
@require_auth
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "AutoSO ready.\n\n"
        "/texture <url> [url ...] [-m prompt|rag] [\"Title\"] — Texture analysis\n"
        "/bucket  <url> [url ...] [-m prompt|rag] [\"Title\"] — Bucket analysis\n"
        "/transcribe <url> [\"Title\"] — Transcribe audio/video\n\n"
        "Default mode: prompt. Use -m rag for the legacy RAG pipeline."
    )
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_bot/test_handlers.py -v`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add autoso/bot/handlers.py tests/test_bot/test_handlers.py
git commit -m "feat(bot): multi-URL + mode + quoted title in _handle_analysis"
```

---

## Task 20: Integration test updates

**Files:**
- Modify: `tests/integration/test_analyze.py`
- Modify: `tests/integration/_helpers.py` (if it has single-URL helpers — inspect first)
- Modify: `autoso/diagnostics/analyze.py` (if it still uses single-URL `run_pipeline` — inspect first)

- [ ] **Step 1: Check current callers of old `store_result` / `run_pipeline` signatures**

Run: `grep -rn "store_result\b\|run_pipeline\b" autoso/ tests/`

Any non-test hit outside `autoso/pipeline/pipeline.py` or `autoso/bot/handlers.py` needs updating. Inspect `autoso/diagnostics/analyze.py` specifically — it's called from `tests/integration/test_analyze.py`.

- [ ] **Step 2: Update `autoso/diagnostics/analyze.py` if needed**

If `analyze.py` calls `run_pipeline(url=..., ...)`, change the call site to `run_pipeline(urls=[url], mode=..., analysis_mode="prompt", provided_title=...)`. Keep its return contract (`{"ok": ..., "output": ..., "title": ...}`) unchanged so integration tests still pass.

If `analyze.run(post, mode)` bypasses `run_pipeline` and does its own orchestration (likely, given it accepts a `Post`), update it to use the new pool/analysis module split: build a pool from the post, call `run_prompt_analysis`, and return the same dict shape. Example:

```python
# autoso/diagnostics/analyze.py — updated run() signature
from autoso.pipeline.flatten import flatten_post_comments
from autoso.pipeline.pool import build_pool
from autoso.pipeline.prompt_analysis import run_prompt_analysis
from autoso.pipeline.llm import configure_llm
from autoso.pipeline.title import infer_title


def run(post, mode: str, analysis_mode: str = "prompt") -> dict:
    try:
        configure_llm()
        if not post.comments:
            return {"ok": False, "skipped": True,
                    "reason": f"No comments to analyse for {post.url}",
                    "error": "empty"}
        flat = flatten_post_comments(post, n_cap=500, source_index=0)
        pool = build_pool([flat], [post])
        title = infer_title(post)
        hg_block = None
        if mode == "bucket":
            try:
                from autoso.pipeline.pipeline import _run_holy_grail
                hg_block = _run_holy_grail()
            except Exception as e:  # Holy Grail missing → skip
                return {"ok": False, "skipped": True, "reason": str(e), "error": "holy_grail"}
        result = run_prompt_analysis(
            mode=mode, title=title, pool=pool, hg_block=hg_block,
        )
        return {"ok": True, "title": title, "output": result.output_clean}
    except Exception as e:
        return {"ok": False, "error": str(e)}
```

(Read the existing file first — adapt the fields/paths to whatever the real implementation already exposes. Do not invent keys that the integration tests don't check.)

- [ ] **Step 3: Run integration tests (skip-gated)**

Run: `pytest tests/integration/test_analyze.py -v`
Expected: all tests that don't need live credentials pass. Live-credential tests (`ANTHROPIC_API_KEY`-gated) skip cleanly unless creds are present.

- [ ] **Step 4: Add new multi-URL integration test**

Append to `tests/integration/test_analyze.py`:

```python
@pytest.mark.integration
def test_texture_multi_url_prompt_mode(tmp_path, monkeypatch):
    """Two cached posts, prompt mode — asserts storage receives both sources."""
    _require_anthropic()

    from unittest.mock import patch as mock_patch
    from autoso.pipeline.pipeline import run_pipeline

    post1 = CANNED_POST
    post2 = CANNED_POST  # reuse; the assertion is on URL count, not content

    with mock_patch(
        "autoso.pipeline.pipeline.scrape",
        side_effect=[("sid-1", post1), ("sid-2", post2)],
    ), mock_patch(
        "autoso.pipeline.pipeline.store_multi_result", return_value="run-xyz",
    ) as mock_store:
        result = run_pipeline(
            urls=["https://a.example/x", "https://b.example/y"],
            mode="texture",
            analysis_mode="prompt",
            provided_title="Integration Multi URL",
        )

    assert result.run_id == "run-xyz"
    _, kwargs = mock_store.call_args
    assert kwargs["urls"] == ["https://a.example/x", "https://b.example/y"]
    assert kwargs["analysis_mode"] == "prompt"
    assert len(kwargs["scrape_ids"]) == 2
```

- [ ] **Step 5: Run full integration suite**

Run: `pytest tests/integration/ -v`
Expected: all tests pass or skip (when credentials absent).

- [ ] **Step 6: Commit**

```bash
git add autoso/diagnostics/analyze.py tests/integration/test_analyze.py
git commit -m "test(integration): update callers to new multi-URL pipeline"
```

---

## Task 21: Full regression sweep

- [ ] **Step 1: Run the complete test suite**

Run: `pytest -v`
Expected: all non-`@pytest.mark.integration` tests pass. Integration tests pass or skip based on credentials.

- [ ] **Step 2: Fix any remaining failures**

If a test fails, do NOT skip or xfail it. Read the error, identify root cause, fix the code (or fix the test if it was asserting pre-Phase-1Y behaviour), commit the fix with a `fix:` message.

- [ ] **Step 3: Sanity-import the bot**

Run: `python -c "from autoso.bot.handlers import texture_handler, bucket_handler, start_handler; print('ok')"`
Expected: `ok` — catches any stale imports left over from the refactor.

- [ ] **Step 4: Commit any fixups**

```bash
git add -A  # only if Step 2 produced fixups
git commit -m "fix: Phase 1Y regressions" || true
```

---

## Task 22: Apply migration in Supabase

**Files:**
- None (manual operational step).

- [ ] **Step 1: Back up current analyses/citations rows**

Open the Supabase SQL editor. Run:

```sql
SELECT COUNT(*) FROM analyses;
SELECT COUNT(*) FROM citations;
```

Record the counts. If either > 0, export to CSV via the Supabase UI before proceeding — the migration begins with `TRUNCATE`.

- [ ] **Step 2: Run the migration**

In the Supabase SQL editor, paste the full contents of `migrations/004_multi_url_analysis.sql` and execute.

- [ ] **Step 3: Verify schema**

Run:

```sql
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'analyses' ORDER BY ordinal_position;

SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'analysis_sources' ORDER BY ordinal_position;

SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'citations' ORDER BY ordinal_position;
```

Expected: `analyses` has no `url`, has `analysis_mode`. `analysis_sources` exists with `(id, analysis_id, url, link_index, scrape_id, created_at)`. `citations` has `source_id`, no `platform`.

- [ ] **Step 4: Smoke test from Telegram**

In the actual bot, send `/texture https://facebook.com/<a-known-post>` and confirm:
- Output arrives.
- In Supabase: 1 `analyses` row with `analysis_mode='prompt'`, 1 `analysis_sources` row, N `citations` rows all carrying `source_id`.

Then send `/texture https://reddit.com/a https://facebook.com/b "Combined"` to confirm multi-URL flow: 1 analysis row, 2 analysis_sources rows, citations with two distinct `source_id`s.

- [ ] **Step 5: Tag the deploy**

```bash
git tag -a phase-1y -m "Phase 1Y: multi-URL LLM analysis"
git push origin phase-1y
```

(Only run `git push` if the user confirms.)

---

## Self-Review

**Spec coverage:**

| Spec section | Task(s) |
|---|---|
| 1. Schema | Task 1 |
| 2. Comment flattening (FlatComment + scaling) | Tasks 2, 3, 4, 5, 6 |
| 3. Pool assembly | Task 7 |
| 4. Analysis modules (shared types + prompt + rag + citation.py trim) | Tasks 9, 10, 11, 12, 13, 14, 15 |
| 5. Pipeline orchestration | Task 17 |
| 6. Storage layer | Task 16 |
| 7. Prompts | Task 8 |
| 8. Bot handler | Tasks 18, 19 |
| 9. Testing | Interleaved throughout (every task has tests); Task 20 for integration |
| 10. Out of scope | Covered by Task 13's `USE_OLLAMA` guard in prompt_analysis |
| 11. Migration plan | Task 22 |

All spec sections are represented.

**Placeholder scan:** None — every code block is literal, file paths are absolute under the repo, commands include expected output.

**Type consistency:**
- `FlatComment(original_id, position, text, thread_context, source_index)` — used identically in flatten, pool, prompt_analysis, rag_analysis. ✓
- `PoolItem(citation_number, flat)` — used identically. ✓
- `Pool(items, posts)` + `.lookup()` — used identically. ✓
- `CitationRecord(citation_number, text, comment_id, position, source_index)` — emitted by both prompt and rag modules, consumed by `store_multi_result`. ✓
- `AnalysisResult(output_cited, output_clean, citations)` — emitted by both analysis modules, consumed by pipeline.py and stored by store_multi_result. ✓
- `run_pipeline(urls, mode, analysis_mode, provided_title)` — same kwargs in bot handler and integration tests. ✓
- `store_multi_result(urls, scrape_ids, mode, analysis_mode, title, analysis)` — same kwargs in pipeline.py and storage tests. ✓

No inconsistencies found.
