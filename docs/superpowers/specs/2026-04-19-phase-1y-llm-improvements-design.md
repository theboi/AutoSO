# Phase 1Y: LLM Improvements Design

**Date:** 2026-04-19
**Status:** Draft

## Overview

Phase 1Y improves the LLM analysis layer on top of Phase 1X's scraping improvements. Four concurrent changes:

1. **Multi-link analyses** — `/texture` and `/bucket` accept multiple URLs in one request, producing a single unified analysis.
2. **Scaled comment pool** — up to 500 comments per link (top-level + replies counted together); total capped at 5000 when link count exceeds 10.
3. **Analysis mode toggle** — `-m prompt` (default, Case 3 from the investigation: direct Anthropic SDK with all comments inline) or `-m rag` (Case 1: existing `CitationQueryEngine` with `similarity_top_k` raised to the comment pool size).
4. **Schema rework** — `analyses` no longer has `url`. New `analysis_sources` junction table. `citations` gain `source_id` so every cited comment is traceable to its URL and scrape record.

### Design drivers

- The investigation ([investigation_results/ANALYSIS.md](../../../investigation_results/ANALYSIS.md)) showed Case 3 (direct prompt, all comments inline, true `system=` message) produces strictly richer output than the current RAG pipeline, with per-bullet `[N]` citations the UI can actually use. Case 1 is kept as an alternative for edge cases (very large pools, comparison runs).
- Citations should be one row per actual comment, not per chunk. Case 3 gives that naturally; Case 1 will too once the flattened-comment pool is indexed whole (no 512-token splitting from within a single comment).
- Phase 1X made scrapes cacheable and traceable (`scrapes` table). Phase 1Y extends that traceability into citations: citation → source → scrape → platform/url.

---

## 1. Schema

### Migration `migrations/004_multi_url_analysis.sql`

```sql
-- Existing analyses rows become orphaned in their current form.
-- Wipe and restart rather than attempt backfill.
TRUNCATE TABLE citations, analyses RESTART IDENTITY CASCADE;

ALTER TABLE analyses DROP COLUMN url;

CREATE TABLE analysis_sources (
    id          UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID    NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    url         TEXT    NOT NULL,
    link_index  INTEGER NOT NULL,
    scrape_id   UUID    REFERENCES scrapes(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_analysis_sources_analysis_id ON analysis_sources (analysis_id);

ALTER TABLE analyses ADD COLUMN analysis_mode TEXT NOT NULL DEFAULT 'prompt'
    CHECK (analysis_mode IN ('prompt', 'rag'));

ALTER TABLE citations ADD COLUMN source_id UUID REFERENCES analysis_sources(id);
ALTER TABLE citations DROP COLUMN platform;   -- derivable via analysis_sources → scrapes
ALTER TABLE citations ADD CONSTRAINT citations_run_citation_unique
    UNIQUE (run_id, citation_number);
```

### Final table shapes

- `analyses (id, mode, title, output, output_cited, analysis_mode, created_at)` — new `analysis_mode TEXT CHECK (analysis_mode IN ('prompt','rag'))` column added in the same migration.
- `analysis_sources (id, analysis_id, url, link_index, scrape_id, created_at)`
- `citations (id, run_id, source_id, citation_number, text, comment_id, position, created_at)`
- `scrapes` — unchanged from Phase 1X.

Constraint: within a single `analysis_id`, `(citation_number)` is unique — enforced by `UNIQUE (run_id, citation_number)` on `citations`. `citation_number` is the global `[N]` the model emitted, 1-indexed across the full pool.

---

## 2. Comment flattening

### `autoso/pipeline/flatten.py` (new)

```python
@dataclass
class FlatComment:
    original_id: str          # Comment.id from the scrape
    position: int             # 0-indexed within this flattened list
    text: str                 # this comment's own text, no prepend
    thread_context: list[str] # preceding messages in the thread; empty for top-level
    source_index: int         # which URL (0-indexed user-provided order)

def flatten_post_comments(post: Post, n_cap: int, source_index: int) -> list[FlatComment]:
    ...
```

**Algorithm:**

Walk `post.comments` in order. For each top-level comment:

1. Emit a `FlatComment` with empty `thread_context`.
2. Walk `subcomments[0:9]` (the first 9 replies). Thread size = parent + 9 replies = 10 messages max.
3. Each emitted reply at index `i` gets `thread_context = [parent.text] + [subcomments[0].text, ..., subcomments[i-1].text]`.
4. Any reply at `subcomments[9]` or later is **dropped** entirely — not emitted, not cited.
5. Stop the outer loop once `len(output) == n_cap`. If the cap is hit mid-thread, the current thread is truncated cleanly at that item; the next top-level is not visited.
6. Deeper nesting (`subcomments` of a reply) is ignored — Phase 1X scrapers flatten past depth 1 already, and any sub-sub-replies encountered here are treated as not present.

### Prompt-inline rendering

Top-level comment:
```
[12] <text>
```

Reply (non-empty `thread_context`):
```
[47] ↳ reply in thread:
  parent: <thread_context[0]>
  · <thread_context[1]>
  · <thread_context[2]>
<text>
```

The format is stable across runs so the model sees the same structure every time.

### `autoso/pipeline/scaling.py` (new)

```python
def comments_per_link(num_links: int) -> int:
    """Max flattened comments per link. Caps total at ~5000 once links > 10."""
    if num_links <= 0:
        raise ValueError("num_links must be >= 1")
    if num_links <= 10:
        return 500
    return 5000 // num_links
```

Quick reference: 10 links → 500 each; 11 → 454; 20 → 250; 50 → 100.

---

## 3. Pool assembly

### `autoso/pipeline/pool.py` (new)

```python
@dataclass
class PoolItem:
    citation_number: int    # 1-indexed, unique across the pool
    flat: FlatComment

@dataclass
class Pool:
    items: list[PoolItem]
    posts: list[Post]       # one per source, aligned to source_index

def build_pool(flattened_per_link: list[list[FlatComment]], posts: list[Post]) -> Pool:
    """Concatenate per-link flattened lists, assign global 1-based citation numbers."""
```

`Pool` exposes `lookup(citation_number) -> PoolItem` and `get_source_index(citation_number) -> int`, used when mapping the model's `[N]` markers back to source records for storage.

---

## 4. Analysis modules

Two modules share a common `AnalysisResult`:

```python
@dataclass
class CitationRecord:
    citation_number: int
    text: str              # the full comment text (no prepend)
    comment_id: str
    position: int
    source_index: int

@dataclass
class AnalysisResult:
    output_cited: str      # raw model output with [N] markers
    output_clean: str      # markers stripped via strip_citation_markers
    citations: list[CitationRecord]
```

### `autoso/pipeline/prompt_analysis.py` (Case 3 — default)

```python
def run_prompt_analysis(mode, title, pool, posts) -> AnalysisResult:
    ...
```

- System message = `TEXTURE_SYSTEM_PROMPT` or `BUCKET_SYSTEM_PROMPT`, passed verbatim as `system=`.
- User message (single):
  ```
  POSTS (N sources):

  [Source 1 — <platform>] <url>
  <post.content>

  [Source 2 — <platform>] <url>
  <post.content>
  ...

  COMMENTS:
  [1] <rendered flat comment>
  [2] <rendered flat comment>
  ...

  <TEXTURE_FORMAT_INSTRUCTION or BUCKET_FORMAT_INSTRUCTION with title filled in>

  After each bullet, append the citation markers [N] for the comments that support it.
  ```
- For `bucket` mode the Holy Grail retrieval runs first (unchanged — it still uses a `CitationQueryEngine` against the separate holy grail index), and its response is inserted as a `BUCKET HOLY GRAIL REFERENCE:` block above the `COMMENTS:` block. This HG retrieval is shared by both analysis modes; it happens in `run_pipeline` before dispatching to prompt/rag analysis, and the HG block is passed into the analysis module.
- Call: `anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY).messages.create(model=config.CLAUDE_MODEL, max_tokens=4096, system=<system>, messages=[{"role": "user", "content": <user_message>}])`.
- Extract `[N]` markers via `re.findall(r"\[(\d+)\]", response_text)`. For each unique marker, look up `PoolItem` in the pool, build a `CitationRecord` with `source_index` from the flat comment.

### `autoso/pipeline/rag_analysis.py` (Case 1 — alternative)

```python
def run_rag_analysis(mode, title, pool, posts) -> AnalysisResult:
    ...
```

- Index the **already-flattened** pool items as llama_index Documents (text = rendered flat comment, metadata = `{comment_id, position, source_index, citation_number}`). This preserves 1-to-1 mapping between citation numbers and comments even though the model sees llama_index's template.
- `build_citation_engine` gains a `citation_chunk_size` kwarg (default stays 512 for holy grail use; rag_analysis passes 4096 so flat comments — even with a full thread prepend — almost always fit in one chunk and don't get split into multiple citation rows). Long outliers that still exceed 4096 tokens produce multiple source nodes sharing the same `comment_id`; the citation-dedup step below collapses them.
- `build_citation_engine(index, similarity_top_k=len(pool.items), system_prompt=<system>, citation_chunk_size=4096)`.
- Query with the same per-source post context + format instruction as prompt mode (without the "append `[N]`" line — RAG attaches citations via source_nodes).
- Citations come from `response.source_nodes`; each source node's metadata contains the fields we need to build `CitationRecord` with `source_index`. Dedupe by `(comment_id, source_index)` so long-comment chunk splits don't inflate the citation count.

`autoso/pipeline/citation.py` shrinks to:
- `build_citation_engine(...)` (kept, used by bucket holy grail + rag mode)
- `strip_citation_markers(text)` (kept, used by both modes)
- Old `extract_citations(response)` / `CitationNode` removed (replaced by per-mode mapping via the `Pool`).

---

## 5. Pipeline orchestration

### `autoso/pipeline/pipeline.py`

```python
def run_pipeline(
    urls: list[str],
    mode: Literal["texture", "bucket"],
    analysis_mode: Literal["prompt", "rag"] = "prompt",
    provided_title: Optional[str] = None,
) -> PipelineResult:
    configure_llm()

    # 1. Scrape via Phase 1X unified entry point (returns (scrape_id, Post)).
    # Sequential — Phase 1X cache absorbs repeat-URL cost within 30-minute windows.
    # Parallelisation is out of scope for this phase (Playwright scrapers are not reentrant-safe).
    sources = [scrape(url) for url in urls]
    posts = [p for _, p in sources]
    scrape_ids = [sid for sid, _ in sources]

    # 2. Flatten with scaling.
    n_cap = comments_per_link(len(urls))
    flattened = [
        flatten_post_comments(post, n_cap, i)
        for i, post in enumerate(posts)
    ]
    if sum(len(fl) for fl in flattened) == 0:
        raise RuntimeError("No comments retrieved from any URL.")

    # 3. Pool.
    pool = build_pool(flattened, posts)

    # 4. Title.
    title = provided_title or posts[0].post_title

    # 5. Analyse.
    if analysis_mode == "prompt":
        analysis = run_prompt_analysis(mode, title, pool, posts)
    else:
        analysis = run_rag_analysis(mode, title, pool, posts)

    # 6. Persist.
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

`PipelineResult` updates: `citation_index: List[CitationNode]` → `citations: List[CitationRecord]`.

---

## 6. Storage layer

### `autoso/storage/supabase.py`

Replace `store_result` with `store_multi_result`:

```python
def store_multi_result(
    urls: list[str],
    scrape_ids: list[str],
    mode: str,
    analysis_mode: str,
    title: str,
    analysis: AnalysisResult,
) -> str:
    """Insert analysis + sources + citations transactionally. Returns run_id."""
```

**Insert order:**

1. `analyses` row — `(id, mode, analysis_mode, title, output, output_cited)`.
2. `analysis_sources` rows — one per URL, `link_index` = 0-based input order, `scrape_id` from the scrape cache.
3. Build `source_index → source_id` map from the `analysis_sources` insert return values.
4. `citations` rows — resolve `source_id` via `source_index` from each `CitationRecord`.

Supabase client's `.insert(...).execute()` returns inserted rows; use that to build the map.

Failure handling: supabase-py has no first-class transaction support; sequential inserts are acceptable because a half-written analysis is still discoverable by `run_id` and can be cleaned up. Any raise inside `store_multi_result` propagates — caller logs and surfaces "error" to Telegram.

---

## 7. Prompts

### `autoso/pipeline/prompts.py`

Fix the contradiction in both `TEXTURE_FORMAT_INSTRUCTION` and `BUCKET_FORMAT_INSTRUCTION`: remove the "`CRITICAL: Do NOT include citation markers`" line. Prompt-mode wants markers; RAG mode strips them after the fact. No instruction change for RAG mode is needed (CitationQueryEngine's own template handles marker output).

Additionally, both format instructions gain an explicit multi-source hint:
```
When multiple sources are provided, the percentages reflect the combined comment pool across all sources.
```
— inserted before the `*Title*` line in each format block.

---

## 8. Bot handler

### `autoso/bot/handlers.py`

New helper:

```python
class ArgParseError(ValueError):
    """Raised with a user-facing message when command parsing fails."""

def _parse_analysis_args(args: list[str]) -> tuple[list[str], str, Optional[str]]:
    """
    Returns (urls, analysis_mode, title).

    Rules:
      - URLs: any arg starting with http:// or https://
      - Mode flag: `-m <value>` or `--mode <value>`, value ∈ {"prompt", "rag"}.
        Default: "prompt".
      - Title: single arg wrapped in matching double or single quotes. May be
        reconstructed from multiple args if Telegram split on spaces inside the
        quoted string — join adjacent args once an opening quote is seen, close
        on matching quote. Quotes stripped before returning.
      - Any arg that is none of the above → raise ArgParseError with usage.
      - At least 1 URL required. More than 50 URLs → reject (practical cap).
    """
```

Telegram passes `context.args` already split on whitespace, so `"My Title With Spaces"` arrives as multiple args. The parser joins them when it sees a quoted token span.

`_handle_analysis` uses this helper, passes `urls` (list) and `analysis_mode` through to `run_pipeline`. The "Processing..." message includes the URL count.

Updated `/start` text:
```
AutoSO ready.

/texture <url> [url ...] [-m prompt|rag] ["Title"] — Texture analysis
/bucket  <url> [url ...] [-m prompt|rag] ["Title"] — Bucket analysis
/transcribe <url> ["Title"] — Transcribe audio/video

Default mode: prompt. Use -m rag for the legacy RAG pipeline.
```

**Output:** still sends `result.output` (the stripped version) — `[N]` markers are never visible in Telegram. Only the Phase 2 UI editor surfaces `output_cited`.

---

## 9. Testing

### Unit tests

- `tests/test_pipeline/test_flatten.py` — threading cap (parent + 9 replies max, 10th dropped), n_cap truncation mid-thread, empty post, single top-level no replies, deeply nested (2+ levels) flattened correctly to thread order.
- `tests/test_pipeline/test_scaling.py` — boundaries: 1, 10, 11, 20, 50 links.
- `tests/test_pipeline/test_pool.py` — global numbering across multi-link, `source_index` preserved, lookup by citation number.
- `tests/test_bot/test_handlers.py` — arg parser: URLs-only, URLs+title, URLs+mode, URLs+mode+title, rejects empty, rejects unknown tokens, rejects too-many URLs.

### Integration tests (marked `@pytest.mark.integration`)

- `test_texture_prompt_multi_url` — two cached posts (reuse Phase 1X scrape cache), prompt mode, asserts output has percentage markers, citations are stored with both source_ids populated.
- `test_texture_rag_multi_url` — same two posts, rag mode, asserts citations populated and `analysis_mode = 'rag'` in the row.
- `test_bucket_skips_if_no_holy_grail` — unchanged behaviour.

Existing canned-post tests (`test_analyze.py`) update: single URL becomes `urls=[CANNED_POST.url]`.

### Investigation parity check

Add a one-off regression script at `investigation_results/run_multi_sanity.py` that loads the cached Phase 1Y fixture from Phase 1X's test post fixture and runs `run_pipeline(urls=[url], mode="texture", analysis_mode="prompt")` to confirm output shape matches the investigation's Case 3 baseline.

---

## 10. Out of scope (explicit)

- Phase 2 UI (citation editor) — not touched here; this spec only ensures the data model supports it.
- New scrapers — already covered by Phase 1X.
- Dynamic retrieval strategies beyond Case 1/Case 3 (hybrid, re-ranking, etc.).
- Ollama/local-model support for prompt mode — `run_prompt_analysis` hard-codes the Anthropic SDK. `USE_OLLAMA=true` continues to work **only** in RAG mode via the existing llama_index abstraction. `run_prompt_analysis` checks `config.USE_OLLAMA` on entry and raises `RuntimeError("prompt mode requires Anthropic API; set USE_OLLAMA=false or use -m rag")` if set.
- Caching of analysis results (pipeline-level).
- Streaming responses to Telegram.

---

## 11. Migration plan

1. Merge the migration SQL — runs `TRUNCATE` of `citations`/`analyses`, then adds `analysis_sources` and `source_id`.
2. Deploy code — the bot rejects any pre-existing pending requests gracefully because the command parser is new.
3. First live runs will repopulate `scrapes` (via Phase 1X cache) and produce fresh `analyses` rows with the new shape.

No backfill of historical analyses — the DB is small, the structure changed meaningfully, and the old `url` column collapses awkwardly into a 1-source junction row anyway. Wipe is cleaner.
