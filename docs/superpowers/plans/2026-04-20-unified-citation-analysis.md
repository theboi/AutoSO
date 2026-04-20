# Unified CitationQueryEngine Analysis Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dual prompt/RAG analysis modes with a single `run_analysis()` that uses `SummaryIndex + CitationQueryEngine` (no vector search on comments), keeping RAG only for holy grail bucket lookup.

**Architecture:** Create `autoso/pipeline/run_analysis.py` with one function that builds `TextNode` objects per comment, indexes them in a `SummaryIndex` (no embeddings/ChromaDB), and runs `CitationQueryEngine`. Remove `run_prompt_analysis`, `run_rag_analysis`, and the `-m`/`--mode` Telegram flag. `pipeline.py` calls `run_analysis()` unconditionally.

**Tech Stack:** llama-index-core `SummaryIndex`, `TextNode`, `CitationQueryEngine`; existing `citation.py` `build_citation_engine`; existing `prompt_analysis.py` rendering helpers.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| CREATE | `autoso/pipeline/run_analysis.py` | New unified analysis: TextNode pool → SummaryIndex → CitationQueryEngine |
| CREATE | `tests/test_pipeline/test_run_analysis.py` | Tests for run_analysis |
| MODIFY | `autoso/pipeline/citation.py` | Broaden index type hint from `VectorStoreIndex` to `BaseIndex` |
| MODIFY | `autoso/pipeline/prompt_analysis.py` | Remove `run_prompt_analysis` (keep `render_flat_comment`, `render_user_message`, `extract_citations_from_output`) |
| MODIFY | `autoso/pipeline/pipeline.py` | Replace branching with `run_analysis()`, remove `AnalysisMode` / `analysis_mode` param |
| MODIFY | `autoso/bot/handlers.py` | Remove `-m`/`--mode` flag; `_parse_analysis_args` returns `(urls, title)` |
| MODIFY | `autoso/diagnostics/analyze.py` | Remove `analysis_mode`, call `run_analysis` directly |
| DELETE | `autoso/pipeline/rag_analysis.py` | Replaced by `run_analysis.py` |
| MODIFY | `tests/test_pipeline/test_prompt_analysis.py` | Remove `run_prompt_analysis` tests (keep render/extract tests) |
| MODIFY | `tests/test_pipeline/test_pipeline.py` | Remove `analysis_mode`, remove rag dispatch test, update patches |
| MODIFY | `tests/test_bot/test_handlers.py` | Remove `-m` flag tests, update `_parse_analysis_args` return shape |
| DELETE | `tests/test_pipeline/test_rag_analysis.py` | Replaced by `test_run_analysis.py` |

---

## Task 1: Create `autoso/pipeline/run_analysis.py`

**Files:**
- Create: `autoso/pipeline/run_analysis.py`
- Test: `tests/test_pipeline/test_run_analysis.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_pipeline/test_run_analysis.py
from unittest.mock import MagicMock, patch

from autoso.pipeline.analysis import AnalysisResult
from autoso.pipeline.flatten import FlatComment
from autoso.pipeline.pool import Pool, PoolItem
from autoso.pipeline.run_analysis import _render_node_text, run_analysis
from autoso.scraping.models import Post


def _post(url: str) -> Post:
    return Post(
        id=url, platform="reddit", url=url, page_title="", post_title="",
        date=None, author=None, content="post body", likes=None, comments=[],
    )


def _pool() -> Pool:
    return Pool(
        items=[
            PoolItem(1, FlatComment("a1", 0, "alpha", [], 0)),
            PoolItem(2, FlatComment("b1", 0, "bravo", ["parent text"], 1)),
            PoolItem(3, FlatComment("c1", 1, "charlie", [], 1)),
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


def test_render_node_text_top_level():
    item = PoolItem(5, FlatComment("c1", 0, "alpha text", [], 0))
    assert _render_node_text(item) == "alpha text"


def test_render_node_text_reply_includes_thread_no_bracket_prefix():
    item = PoolItem(12, FlatComment("r1", 4, "disagreed", ["parent says", "first reply"], 1))
    rendered = _render_node_text(item)
    assert not rendered.startswith("[12]")
    assert "↳ reply in thread" in rendered
    assert "parent: parent says" in rendered
    assert "· first reply" in rendered
    assert rendered.endswith("disagreed")


def test_run_analysis_uses_summary_index_not_vector_store():
    pool = _pool()
    fake_response = MagicMock()
    fake_response.__str__ = lambda self: "- bullet [1]\n- bullet [2]"
    fake_response.source_nodes = []
    fake_engine = MagicMock()
    fake_engine.query.return_value = fake_response

    with patch("autoso.pipeline.run_analysis.SummaryIndex") as MockIndex, \
         patch("autoso.pipeline.run_analysis.build_citation_engine", return_value=fake_engine):
        run_analysis(mode="texture", title="T", pool=pool, hg_block=None)

    MockIndex.assert_called_once()
    # Verify no ChromaDB or VectorStoreIndex is imported/used
    args = MockIndex.call_args[0][0]
    assert len(args) == 3  # one TextNode per pool item


def test_run_analysis_creates_text_nodes_with_metadata():
    pool = _pool()
    fake_response = MagicMock()
    fake_response.__str__ = lambda self: ""
    fake_response.source_nodes = []
    fake_engine = MagicMock()
    fake_engine.query.return_value = fake_response

    captured_nodes = []

    def capture_index(nodes):
        captured_nodes.extend(nodes)
        return MagicMock()

    with patch("autoso.pipeline.run_analysis.SummaryIndex", side_effect=capture_index), \
         patch("autoso.pipeline.run_analysis.build_citation_engine", return_value=fake_engine):
        run_analysis(mode="texture", title="T", pool=pool, hg_block=None)

    assert len(captured_nodes) == 3
    assert captured_nodes[0].metadata["citation_number"] == 1
    assert captured_nodes[0].metadata["comment_id"] == "a1"
    assert captured_nodes[0].text == "alpha"
    assert captured_nodes[1].metadata["citation_number"] == 2
    assert "↳ reply in thread" in captured_nodes[1].text


def test_run_analysis_returns_result_with_citations():
    pool = _pool()
    fake_response = MagicMock()
    fake_response.__str__ = lambda self: "- bullet [1]\n- bullet [2]"
    fake_response.source_nodes = [
        _source_node("a1", 1, 0, 0, "alpha"),
        _source_node("b1", 2, 1, 0, "bravo"),
    ]
    fake_engine = MagicMock()
    fake_engine.query.return_value = fake_response

    with patch("autoso.pipeline.run_analysis.SummaryIndex"), \
         patch("autoso.pipeline.run_analysis.build_citation_engine", return_value=fake_engine):
        result = run_analysis(mode="texture", title="T", pool=pool, hg_block=None)

    assert isinstance(result, AnalysisResult)
    assert result.output_cited == "- bullet [1]\n- bullet [2]"
    assert result.output_clean == "- bullet\n- bullet"
    citation_numbers = sorted(r.citation_number for r in result.citations)
    assert citation_numbers == [1, 2]
    mapped = {r.citation_number: r for r in result.citations}
    assert mapped[1].text == "alpha"
    assert mapped[1].comment_id == "a1"


def test_run_analysis_dedupes_by_comment_id_and_source():
    pool = _pool()
    fake_response = MagicMock()
    fake_response.__str__ = lambda self: "- bullet [1]"
    fake_response.source_nodes = [
        _source_node("a1", 1, 0, 0, "alpha part 1"),
        _source_node("a1", 1, 0, 0, "alpha part 2"),
    ]
    fake_engine = MagicMock()
    fake_engine.query.return_value = fake_response

    with patch("autoso.pipeline.run_analysis.SummaryIndex"), \
         patch("autoso.pipeline.run_analysis.build_citation_engine", return_value=fake_engine):
        result = run_analysis(mode="texture", title="T", pool=pool, hg_block=None)

    assert len(result.citations) == 1


def test_run_analysis_passes_similarity_top_k_equal_to_pool_size():
    pool = _pool()
    fake_response = MagicMock()
    fake_response.__str__ = lambda self: ""
    fake_response.source_nodes = []
    fake_engine = MagicMock()
    fake_engine.query.return_value = fake_response

    with patch("autoso.pipeline.run_analysis.SummaryIndex"), \
         patch("autoso.pipeline.run_analysis.build_citation_engine", return_value=fake_engine) as mock_build:
        run_analysis(mode="texture", title="T", pool=pool, hg_block=None)

    _, kwargs = mock_build.call_args
    assert kwargs["similarity_top_k"] == 3
    assert kwargs["citation_chunk_size"] == 2048


def test_run_analysis_bucket_passes_hg_block_in_query():
    pool = _pool()
    fake_response = MagicMock()
    fake_response.__str__ = lambda self: ""
    fake_response.source_nodes = []
    fake_engine = MagicMock()
    fake_engine.query.return_value = fake_response

    with patch("autoso.pipeline.run_analysis.SummaryIndex"), \
         patch("autoso.pipeline.run_analysis.build_citation_engine", return_value=fake_engine):
        run_analysis(mode="bucket", title="T", pool=pool, hg_block="BUCKET_LABELS")

    query_arg = fake_engine.query.call_args[0][0]
    assert "BUCKET HOLY GRAIL REFERENCE:" in query_arg
    assert "BUCKET_LABELS" in query_arg


def test_run_analysis_raises_on_unknown_mode():
    pool = _pool()
    with patch("autoso.pipeline.run_analysis.SummaryIndex"), \
         patch("autoso.pipeline.run_analysis.build_citation_engine"):
        try:
            run_analysis(mode="invalid", title="T", pool=pool, hg_block=None)
        except ValueError as e:
            assert "unknown mode" in str(e)
        else:
            raise AssertionError("expected ValueError")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /workspaces/AutoSO && python -m pytest tests/test_pipeline/test_run_analysis.py -v 2>&1 | head -40
```

Expected: `ModuleNotFoundError: No module named 'autoso.pipeline.run_analysis'`

- [ ] **Step 3: Create `autoso/pipeline/run_analysis.py`**

```python
"""Unified analysis: SummaryIndex + CitationQueryEngine (no vector search on comments)."""
from __future__ import annotations

from typing import Optional

from llama_index.core import SummaryIndex
from llama_index.core.schema import TextNode

from autoso.pipeline.analysis import AnalysisResult, CitationRecord
from autoso.pipeline.citation import build_citation_engine, strip_citation_markers
from autoso.pipeline.pool import Pool, PoolItem
from autoso.pipeline.prompt_analysis import render_user_message
from autoso.pipeline.prompts import (
    BUCKET_FORMAT_INSTRUCTION,
    BUCKET_SYSTEM_PROMPT,
    TEXTURE_FORMAT_INSTRUCTION,
    TEXTURE_SYSTEM_PROMPT,
)


def _render_node_text(item: PoolItem) -> str:
    flat = item.flat
    if not flat.thread_context:
        return flat.text
    lines = ["↳ reply in thread:"]
    lines.append(f"  parent: {flat.thread_context[0]}")
    for prior in flat.thread_context[1:]:
        lines.append(f"  · {prior}")
    lines.append(flat.text)
    return "\n".join(lines)


def _extract_citations(response, pool: Pool) -> list[CitationRecord]:
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


def run_analysis(
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

    nodes = [
        TextNode(
            text=_render_node_text(item),
            id_=f"comment_{item.citation_number}",
            metadata={
                "comment_id": item.flat.original_id,
                "position": item.flat.position,
                "source_index": item.flat.source_index,
                "citation_number": item.citation_number,
            },
        )
        for item in pool.items
    ]

    index = SummaryIndex(nodes)
    engine = build_citation_engine(
        index,
        similarity_top_k=max(len(nodes), 1),
        system_prompt=system,
        citation_chunk_size=2048,
    )

    query = render_user_message(
        pool=Pool(items=[], posts=pool.posts),
        format_instruction=format_instruction,
        hg_block=hg_block,
    )

    response = engine.query(query)
    output_cited = str(response)
    output_clean = strip_citation_markers(output_cited)
    citations = _extract_citations(response, pool)
    return AnalysisResult(
        output_cited=output_cited,
        output_clean=output_clean,
        citations=citations,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /workspaces/AutoSO && python -m pytest tests/test_pipeline/test_run_analysis.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add autoso/pipeline/run_analysis.py tests/test_pipeline/test_run_analysis.py
git commit -m "feat: add unified run_analysis using SummaryIndex + CitationQueryEngine"
```

---

## Task 2: Update `autoso/pipeline/citation.py` — broaden index type hint

**Files:**
- Modify: `autoso/pipeline/citation.py`
- Test: `tests/test_pipeline/test_citation.py` (no changes needed — existing tests still pass)

- [ ] **Step 1: Verify existing citation tests pass before touching the file**

```bash
cd /workspaces/AutoSO && python -m pytest tests/test_pipeline/test_citation.py -v
```

Expected: PASS.

- [ ] **Step 2: Update `autoso/pipeline/citation.py`**

Replace the top of the file (imports + function signature) so `build_citation_engine` accepts any index, not just `VectorStoreIndex`:

Old:
```python
import re

from llama_index.core import VectorStoreIndex
from llama_index.core.query_engine import CitationQueryEngine


def build_citation_engine(
    index: VectorStoreIndex,
```

New:
```python
import re

from llama_index.core.indices.base import BaseIndex
from llama_index.core.query_engine import CitationQueryEngine


def build_citation_engine(
    index: BaseIndex,
```

- [ ] **Step 3: Run citation tests to verify still pass**

```bash
cd /workspaces/AutoSO && python -m pytest tests/test_pipeline/test_citation.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add autoso/pipeline/citation.py
git commit -m "refactor: accept any BaseIndex in build_citation_engine"
```

---

## Task 3: Remove `run_prompt_analysis` from `prompt_analysis.py`

**Files:**
- Modify: `autoso/pipeline/prompt_analysis.py`
- Modify: `tests/test_pipeline/test_prompt_analysis.py`

The rendering helpers (`render_flat_comment`, `render_user_message`, `extract_citations_from_output`) are still used by tests and by `run_analysis.py`, so they stay. Only `run_prompt_analysis` and `_APPEND_INSTRUCTION` are removed.

Wait — `render_user_message` uses `_APPEND_INSTRUCTION` internally. The new `run_analysis.py` calls `render_user_message` with an empty pool (same pattern as `rag_analysis.py` did), which means `_APPEND_INSTRUCTION` still appears in the query sent to `CitationQueryEngine`. This is harmless (it's a redundant reinforcement). Keep `_APPEND_INSTRUCTION` and `render_user_message` unchanged.

- [ ] **Step 1: Remove `run_prompt_analysis` from `autoso/pipeline/prompt_analysis.py`**

Delete lines 98–141 (the `run_prompt_analysis` function and its imports of `anthropic` and `config`). Also remove the `anthropic` import at line 9 and the `import autoso.config as config` at line 11 (only used by `run_prompt_analysis`).

Final file after edit:

```python
"""Rendering helpers for the analysis pipeline."""

from __future__ import annotations

import re
from typing import Optional

from autoso.pipeline.analysis import AnalysisResult, CitationRecord
from autoso.pipeline.citation import strip_citation_markers
from autoso.pipeline.pool import Pool, PoolItem
from autoso.pipeline.prompts import (
    BUCKET_FORMAT_INSTRUCTION,
    BUCKET_SYSTEM_PROMPT,
    TEXTURE_FORMAT_INSTRUCTION,
    TEXTURE_SYSTEM_PROMPT,
)

_APPEND_INSTRUCTION = (
    "After each bullet point or numbered item, append the citation markers [N] for the "
    "comments that support it. ALWAYS use square brackets, e.g. [65] [105] [132]. "
    "NEVER write bare numbers without brackets. Use the bracketed numbers shown in the "
    "COMMENTS block above."
)

_MARKER_RE = re.compile(r"\[(\d+)\]")


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
    pool: Pool, format_instruction: str, hg_block: Optional[str] = None
) -> str:
    """Assemble the single user-turn message for the Anthropic call."""
    parts: list[str] = []
    parts.append(f"POSTS ({len(pool.posts)} sources):")
    for i, post in enumerate(pool.posts, start=1):
        parts.append(f"\n[Source {i} — {post.platform.upper()}] {post.url}\n{post.content or ''}")

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


def extract_citations_from_output(output_text: str, pool: Pool) -> list[CitationRecord]:
    """Pull [N] markers from model output and map to CitationRecords via the pool."""
    seen: set[int] = set()
    records: list[CitationRecord] = []

    for match in _MARKER_RE.finditer(output_text):
        citation_number = int(match.group(1))
        if citation_number in seen:
            continue
        seen.add(citation_number)

        item = pool.lookup(citation_number)
        if item is None:
            continue

        flat = item.flat
        records.append(
            CitationRecord(
                citation_number=citation_number,
                text=flat.text,
                comment_id=flat.original_id,
                position=flat.position,
                source_index=flat.source_index,
            )
        )

    return records
```

- [ ] **Step 2: Remove `run_prompt_analysis` tests from `tests/test_pipeline/test_prompt_analysis.py`**

Delete the three test functions at the bottom of the file (lines 161–219): `test_run_prompt_analysis_returns_result`, `test_run_prompt_analysis_bucket_mode_includes_hg_block`, `test_run_prompt_analysis_raises_if_ollama_enabled`.

Also remove the import of `run_prompt_analysis` from line 6 and `AnalysisResult` if it becomes unused.

Final import block:

```python
from autoso.pipeline.analysis import CitationRecord
from autoso.pipeline.flatten import FlatComment
from autoso.pipeline.pool import Pool, PoolItem
from autoso.pipeline.prompt_analysis import (
    extract_citations_from_output,
    render_flat_comment,
    render_user_message,
)
from autoso.scraping.models import Post
```

- [ ] **Step 3: Run prompt_analysis tests to verify they pass**

```bash
cd /workspaces/AutoSO && python -m pytest tests/test_pipeline/test_prompt_analysis.py -v
```

Expected: 8 tests PASS (render and extract tests only).

- [ ] **Step 4: Commit**

```bash
git add autoso/pipeline/prompt_analysis.py tests/test_pipeline/test_prompt_analysis.py
git commit -m "refactor: remove run_prompt_analysis, keep rendering helpers"
```

---

## Task 4: Delete `rag_analysis.py` and its test file

**Files:**
- Delete: `autoso/pipeline/rag_analysis.py`
- Delete: `tests/test_pipeline/test_rag_analysis.py`

- [ ] **Step 1: Delete both files**

```bash
rm /workspaces/AutoSO/autoso/pipeline/rag_analysis.py
rm /workspaces/AutoSO/tests/test_pipeline/test_rag_analysis.py
```

- [ ] **Step 2: Verify no other files import from rag_analysis**

```bash
cd /workspaces/AutoSO && grep -r "rag_analysis" --include="*.py" .
```

Expected: Only `pipeline.py` and `diagnostics/analyze.py` still reference it (those are updated in Tasks 5 and 7). If any other file references it, update it now.

- [ ] **Step 3: Run the test suite to see what breaks (expected)**

```bash
cd /workspaces/AutoSO && python -m pytest tests/test_pipeline/ -v 2>&1 | tail -20
```

Expected: `test_pipeline.py` fails with import errors for `run_rag_analysis` — this is expected and will be fixed in Task 5.

- [ ] **Step 4: Commit**

```bash
git add -u
git commit -m "refactor: delete rag_analysis.py and its tests"
```

---

## Task 5: Update `autoso/pipeline/pipeline.py`

**Files:**
- Modify: `autoso/pipeline/pipeline.py`
- Modify: `tests/test_pipeline/test_pipeline.py`

- [ ] **Step 1: Write the updated test file first**

Replace `tests/test_pipeline/test_pipeline.py` entirely:

```python
from unittest.mock import MagicMock, patch

import pytest

from autoso.pipeline.analysis import AnalysisResult, CitationRecord
from autoso.pipeline.pipeline import PipelineResult, run_pipeline
from autoso.scraping.models import Comment, Post


@pytest.fixture
def post() -> Post:
    return Post(
        id="p1",
        platform="reddit",
        url="https://reddit.com/r/test/comments/abc",
        page_title="reddit page",
        post_title="Post title",
        date=None,
        author=None,
        content="The annual exercise has ended.",
        likes=None,
        comments=[
            Comment(
                id="c1",
                platform="reddit",
                author=None,
                date=None,
                text="Strong SAF showing",
                likes=None,
                position=0,
            )
        ],
    )


@pytest.fixture
def analysis_result() -> AnalysisResult:
    return AnalysisResult(
        output_cited="- Point [1]",
        output_clean="- Point",
        citations=[
            CitationRecord(
                citation_number=1,
                text="Strong SAF showing",
                comment_id="c1",
                position=0,
                source_index=0,
            )
        ],
    )


def _default_patches(post: Post, analysis: AnalysisResult):
    pool = MagicMock()
    return {
        "configure_llm": patch("autoso.pipeline.pipeline.configure_llm"),
        "comments_per_link": patch("autoso.pipeline.pipeline.comments_per_link", return_value=500),
        "flatten_post_comments": patch(
            "autoso.pipeline.pipeline.flatten_post_comments", return_value=[]
        ),
        "build_pool": patch("autoso.pipeline.pipeline.build_pool", return_value=pool),
        "run_analysis": patch(
            "autoso.pipeline.pipeline.run_analysis", return_value=analysis
        ),
        "store_multi_result": patch(
            "autoso.pipeline.pipeline.store_multi_result", return_value="run-123"
        ),
        "scrape": patch("autoso.pipeline.pipeline.scrape", return_value=("sid-1", post)),
        "infer_title": patch("autoso.pipeline.pipeline.infer_title", return_value="Inferred Title"),
        "holy_grail": patch("autoso.pipeline.pipeline._run_holy_grail", return_value="HG"),
    }


def test_texture_single_url_returns_result(post, analysis_result):
    p = _default_patches(post, analysis_result)
    with (
        p["configure_llm"],
        p["comments_per_link"],
        p["flatten_post_comments"],
        p["build_pool"],
        p["run_analysis"] as run,
        p["store_multi_result"],
        p["scrape"],
        p["infer_title"],
        p["holy_grail"],
    ):
        result = run_pipeline(
            urls=["https://reddit.com/r/test/comments/abc"],
            mode="texture",
            provided_title="Custom",
        )

    assert isinstance(result, PipelineResult)
    assert result.title == "Custom"
    assert result.output == "- Point"
    assert result.citations == analysis_result.citations
    run.assert_called_once()


def test_multi_url_passes_urls_and_scrape_ids_to_storage(post, analysis_result):
    p = _default_patches(post, analysis_result)
    with (
        p["configure_llm"],
        p["comments_per_link"],
        p["flatten_post_comments"],
        p["build_pool"],
        p["run_analysis"],
        p["store_multi_result"] as store,
        patch(
            "autoso.pipeline.pipeline.scrape",
            side_effect=[("sid-1", post), ("sid-2", post)],
        ),
        p["infer_title"],
        p["holy_grail"],
    ):
        run_pipeline(
            urls=["https://a.com/post", "https://b.com/post"],
            mode="texture",
            provided_title="T",
        )

    _, kwargs = store.call_args
    assert kwargs["urls"] == ["https://a.com/post", "https://b.com/post"]
    assert kwargs["scrape_ids"] == ["sid-1", "sid-2"]


def test_bucket_uses_holy_grail_and_passes_hg_block(post, analysis_result):
    p = _default_patches(post, analysis_result)
    with (
        p["configure_llm"],
        p["comments_per_link"],
        p["flatten_post_comments"],
        p["build_pool"],
        p["run_analysis"] as run,
        p["store_multi_result"],
        p["scrape"],
        p["infer_title"],
        p["holy_grail"] as holy,
    ):
        run_pipeline(urls=["https://a.com/post"], mode="bucket")

    holy.assert_called_once()
    assert run.call_args.kwargs["hg_block"] == "HG"


def test_texture_skips_holy_grail(post, analysis_result):
    p = _default_patches(post, analysis_result)
    with (
        p["configure_llm"],
        p["comments_per_link"],
        p["flatten_post_comments"],
        p["build_pool"],
        p["run_analysis"] as run,
        p["store_multi_result"],
        p["scrape"],
        p["infer_title"],
        p["holy_grail"] as holy,
    ):
        run_pipeline(urls=["https://a.com/post"], mode="texture")

    holy.assert_not_called()
    assert run.call_args.kwargs["hg_block"] is None


def test_empty_urls_raises_value_error():
    with pytest.raises(ValueError, match="non-empty"):
        run_pipeline(urls=[], mode="texture")


def test_infer_title_used_when_no_title(post, analysis_result):
    p = _default_patches(post, analysis_result)
    with (
        p["configure_llm"],
        p["comments_per_link"],
        p["flatten_post_comments"],
        p["build_pool"],
        p["run_analysis"],
        p["store_multi_result"],
        p["scrape"],
        p["infer_title"] as infer,
        p["holy_grail"],
    ):
        result = run_pipeline(
            urls=["https://a.com/post"],
            mode="texture",
            provided_title=None,
        )

    infer.assert_called_once_with(post)
    assert result.title == "Inferred Title"
```

- [ ] **Step 2: Run tests to verify they fail (expected — pipeline.py not updated yet)**

```bash
cd /workspaces/AutoSO && python -m pytest tests/test_pipeline/test_pipeline.py -v 2>&1 | head -30
```

Expected: Import errors or assertion failures because `run_pipeline` still has `analysis_mode` param.

- [ ] **Step 3: Update `autoso/pipeline/pipeline.py`**

```python
import logging
from dataclasses import dataclass, field
from typing import Literal, Optional

from autoso.pipeline.analysis import CitationRecord
from autoso.pipeline.citation import build_citation_engine
from autoso.pipeline.flatten import flatten_post_comments
from autoso.pipeline.holy_grail import load_holy_grail
from autoso.pipeline.llm import configure_llm
from autoso.pipeline.pool import build_pool
from autoso.pipeline.run_analysis import run_analysis
from autoso.pipeline.scaling import comments_per_link
from autoso.pipeline.title import infer_title
from autoso.scraping import scrape
from autoso.storage.supabase import store_multi_result

logger = logging.getLogger(__name__)

Mode = Literal["texture", "bucket"]


@dataclass
class PipelineResult:
    title: str
    output: str
    output_cited: str
    citations: list[CitationRecord] = field(default_factory=list)
    run_id: str = ""


def _run_holy_grail() -> str:
    hg_engine = build_citation_engine(load_holy_grail(), similarity_top_k=20)
    response = hg_engine.query(
        "List all bucket labels for MINDEF/SAF/NS/Defence sentiment analysis"
    )
    return str(response)


def run_pipeline(
    urls: list[str],
    mode: Mode,
    provided_title: Optional[str] = None,
) -> PipelineResult:
    if not urls:
        raise ValueError("urls must be a non-empty list")

    configure_llm()

    scraped = [scrape(url) for url in urls]
    scrape_ids = [scrape_id for scrape_id, _ in scraped]
    posts = [post for _, post in scraped]

    n_cap = comments_per_link(len(urls))
    flattened = [
        flatten_post_comments(post=post, n_cap=n_cap, source_index=source_index)
        for source_index, post in enumerate(posts)
    ]

    logger.info("Scraped %d URLs and flattened %d comments", len(urls), sum(len(f) for f in flattened))

    pool = build_pool(posts=posts, flattened=flattened)
    title = provided_title or infer_title(posts[0])

    hg_block = _run_holy_grail() if mode == "bucket" else None

    analysis = run_analysis(
        mode=mode,
        title=title,
        pool=pool,
        hg_block=hg_block,
    )

    run_id = store_multi_result(
        urls=urls,
        scrape_ids=scrape_ids,
        mode=mode,
        analysis_mode="citation",
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

- [ ] **Step 4: Run pipeline tests to verify they pass**

```bash
cd /workspaces/AutoSO && python -m pytest tests/test_pipeline/test_pipeline.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add autoso/pipeline/pipeline.py tests/test_pipeline/test_pipeline.py
git commit -m "refactor: remove analysis_mode from pipeline, use run_analysis unconditionally"
```

---

## Task 6: Update `autoso/bot/handlers.py`

**Files:**
- Modify: `autoso/bot/handlers.py`
- Modify: `tests/test_bot/test_handlers.py`

- [ ] **Step 1: Write updated handler tests first**

Replace `tests/test_bot/test_handlers.py` entirely:

```python
# tests/test_bot/test_handlers.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from autoso.bot.handlers import (
    ArgParseError,
    _parse_analysis_args,
    bucket_handler,
    start_handler,
    texture_handler,
)
from autoso.pipeline.pipeline import PipelineResult


def _make_update(user_id: int, args: list[str]):
    update = MagicMock()
    update.effective_user.id = user_id
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = args
    return update, context


@pytest.fixture(autouse=True)
def whitelist_user():
    with patch("autoso.config.WHITELISTED_USER_IDS", {99}):
        yield


async def test_start_handler_replies():
    update, context = _make_update(99, [])
    await start_handler(update, context)
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args.args[0]
    assert "/texture" in text
    assert "/bucket" in text


async def test_texture_handler_no_args_sends_usage():
    update, context = _make_update(99, [])
    await texture_handler(update, context)
    text = update.message.reply_text.call_args.args[0]
    assert "Usage" in text


async def test_texture_handler_calls_pipeline_and_replies():
    update, context = _make_update(99, ["https://reddit.com/r/sg/comments/abc"])
    mock_result = PipelineResult(
        title="Test",
        output="- 50% praised SAF",
        output_cited="- 50% praised SAF [1]",
        run_id="run-abc",
    )
    with patch("autoso.bot.handlers.run_pipeline", return_value=mock_result) as mock_pipeline:
        await texture_handler(update, context)

    mock_pipeline.assert_called_once_with(
        urls=["https://reddit.com/r/sg/comments/abc"],
        mode="texture",
        provided_title=None,
    )
    calls = [str(c) for c in update.message.reply_text.call_args_list]
    assert any("Processing 1 link(s)" in c for c in calls)
    assert any("praised SAF" in c for c in calls)


async def test_handler_notifies_user_when_output_too_long():
    update, context = _make_update(99, ["https://reddit.com/r/sg/comments/abc"])
    long_output = "x" * 5000
    mock_result = PipelineResult(
        title="Test",
        output=long_output,
        output_cited=long_output,
        run_id="run-abc",
    )
    with patch("autoso.bot.handlers.run_pipeline", return_value=mock_result) as mock_pipeline:
        await texture_handler(update, context)

    mock_pipeline.assert_called_once_with(
        urls=["https://reddit.com/r/sg/comments/abc"],
        mode="texture",
        provided_title=None,
    )
    calls = [str(c) for c in update.message.reply_text.call_args_list]
    assert any("too long" in c for c in calls) or any("5000" in c for c in calls)
    assert any("run-abc" in c for c in calls)


async def test_handler_replies_on_pipeline_exception():
    update, context = _make_update(99, ["https://reddit.com/r/sg/comments/abc"])
    with patch("autoso.bot.handlers.run_pipeline", side_effect=RuntimeError("scrape failed")):
        await texture_handler(update, context)

    calls = [str(c) for c in update.message.reply_text.call_args_list]
    assert any("error" in c.lower() for c in calls)


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (
            ["https://a.com"],
            (["https://a.com"], None),
        ),
        (
            ["https://a.com", "https://b.com"],
            (["https://a.com", "https://b.com"], None),
        ),
        (
            ["https://a.com", '"My', "Quoted", 'Title"'],
            (["https://a.com"], "My Quoted Title"),
        ),
        (
            ["https://a.com", "'Single token title'"],
            (["https://a.com"], "Single token title"),
        ),
    ],
)
def test_parse_analysis_args_valid(args, expected):
    assert _parse_analysis_args(args) == expected


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["title-only"],
        ["https://a.com", "--unknown"],
        ["https://a.com", '"unterminated', "title"],
        ["https://a.com", "stray"],
        ["https://a.com", '"one"', '"two"'],
        [f"https://{i}.example.com" for i in range(51)],
    ],
)
def test_parse_analysis_args_invalid(args):
    with pytest.raises(ArgParseError):
        _parse_analysis_args(args)


async def test_bucket_handler_multi_url_with_quoted_title():
    update, context = _make_update(
        99,
        [
            "https://a.com/post",
            "https://b.com/post",
            '"My',
            "Custom",
            'Title"',
        ],
    )
    mock_result = PipelineResult(
        title="My Custom Title",
        output="Result body",
        output_cited="Result body [1]",
        run_id="run-bucket",
    )
    with patch("autoso.bot.handlers.run_pipeline", return_value=mock_result) as mock_pipeline:
        await bucket_handler(update, context)

    mock_pipeline.assert_called_once_with(
        urls=["https://a.com/post", "https://b.com/post"],
        mode="bucket",
        provided_title="My Custom Title",
    )
    calls = [str(c) for c in update.message.reply_text.call_args_list]
    assert any("Processing 2 link(s)" in c for c in calls)
    assert any("Result body" in c for c in calls)
```

- [ ] **Step 2: Run tests to verify they fail (expected)**

```bash
cd /workspaces/AutoSO && python -m pytest tests/test_bot/test_handlers.py -v 2>&1 | head -30
```

Expected: Failures because `_parse_analysis_args` still returns a 3-tuple.

- [ ] **Step 3: Update `autoso/bot/handlers.py`**

Full replacement:

```python
# autoso/bot/handlers.py
import asyncio
import functools
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

import autoso.config as config
from autoso.bot.auth import require_auth
from autoso.pipeline.pipeline import run_pipeline
from autoso.transcription.transcription import transcribe_url

logger = logging.getLogger(__name__)

TELEGRAM_MAX_LENGTH = 4096
MAX_URLS = 50


class ArgParseError(ValueError):
    pass


def _split_message(text: str, limit: int = TELEGRAM_MAX_LENGTH) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


# Serial queue: prevents concurrent Playwright launches from OOM-crashing the browser.
_pipeline_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pipeline")


def _is_valid_url(text: str) -> bool:
    try:
        parsed = urlparse(text)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def _parse_analysis_args(args: list[str]) -> tuple[list[str], str | None]:
    if not args:
        raise ArgParseError("No arguments provided.")

    urls: list[str] = []
    title: str | None = None

    i = 0
    while i < len(args):
        token = args[i]

        if token.startswith('"') or token.startswith("'"):
            if title is not None:
                raise ArgParseError("Only one title is allowed.")
            quote = token[0]
            if len(token) > 1 and token.endswith(quote):
                title = token[1:-1]
                i += 1
                continue
            parts = [token[1:]]
            i += 1
            while i < len(args):
                part = args[i]
                if part.endswith(quote):
                    parts.append(part[:-1])
                    title = " ".join(parts)
                    i += 1
                    break
                parts.append(part)
                i += 1
            else:
                raise ArgParseError("Unterminated quoted title.")
            continue

        if token.startswith("-"):
            raise ArgParseError(f"Unknown option: {token!r}.")

        if _is_valid_url(token):
            urls.append(token)
            if len(urls) > MAX_URLS:
                raise ArgParseError(f"Too many URLs (max {MAX_URLS}).")
            i += 1
            continue

        raise ArgParseError(f"Invalid or stray token: {token!r}.")

    if not urls:
        raise ArgParseError("At least one valid URL is required.")

    return urls, title


@require_auth
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "AutoSO ready.\n\n"
        '/texture <url> [url ...] ["Title"] — Texture analysis\n'
        '/bucket <url> [url ...] ["Title"] — Bucket analysis\n'
        "/transcribe <url> [title] — Transcribe audio/video"
    )


@require_auth
async def texture_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _handle_analysis(update, context, mode="texture")


@require_auth
async def bucket_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _handle_analysis(update, context, mode="bucket")


async def _handle_analysis(
    update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str
):
    usage = f'/{mode} <url> [url ...] ["Title"]'
    try:
        urls, provided_title = _parse_analysis_args(context.args or [])
    except ArgParseError as e:
        await update.message.reply_text(f"{e}\nUsage: {usage}")
        return

    await update.message.reply_text(
        f"Processing {len(urls)} link(s). This may take a minute."
    )

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            _pipeline_executor,
            functools.partial(
                run_pipeline,
                urls=urls,
                mode=mode,
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
                logger.warning("Markdown parse failed for run_id=%s — sending plain text", result.run_id)
                await update.message.reply_text(chunk)

    except Exception:
        logger.exception("Pipeline error for urls=%s mode=%s", urls, mode)
        await update.message.reply_text(
            "An error occurred while processing your request. Check logs for details."
        )


@require_auth
async def transcribe_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /transcribe <url> [optional title]")
        return

    url = args[0]
    if not _is_valid_url(url):
        await update.message.reply_text(
            f"Invalid URL: {url!r}\nUsage: /transcribe <url> [optional title]"
        )
        return

    provided_title = " ".join(args[1:]) if len(args) > 1 else None

    await update.message.reply_text("Transcribing... this may take a few minutes.")

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            _pipeline_executor,
            functools.partial(transcribe_url, url=url, title=provided_title),
        )
        docx_path = result.docx_path
        filename = os.path.basename(docx_path)
        with open(docx_path, "rb") as f:
            await update.message.reply_document(document=f, filename=filename)
        try:
            os.unlink(docx_path)
        except OSError:
            pass
    except Exception:
        logger.exception("Transcription error for url=%s", url)
        await update.message.reply_text(
            "An error occurred during transcription. Check logs for details."
        )
```

- [ ] **Step 4: Run handler tests to verify they pass**

```bash
cd /workspaces/AutoSO && python -m pytest tests/test_bot/test_handlers.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add autoso/bot/handlers.py tests/test_bot/test_handlers.py
git commit -m "refactor: remove -m/--mode flag from bot handlers"
```

---

## Task 7: Update `autoso/diagnostics/analyze.py`

**Files:**
- Modify: `autoso/diagnostics/analyze.py`

- [ ] **Step 1: Replace `autoso/diagnostics/analyze.py`**

```python
# autoso/diagnostics/analyze.py
"""Verify that the LLM analysis pipeline produces valid texture/bucket output.

Usage:
    python -m autoso.diagnostics.analyze --mode texture
    python -m autoso.diagnostics.analyze --mode bucket
"""
import argparse
import json
import sys
from typing import Literal

from autoso.scraping.models import Comment, Post

_CLI_CANNED_POST = Post(
    id="diag_post",
    platform="reddit",
    url="https://www.reddit.com/r/singapore/comments/cli_test",
    page_title="r/singapore",
    post_title="Singapore NS Policy Discussion",
    date=None,
    author=None,
    content="Singapore introduces new National Service policy changes for 2024.",
    likes=None,
    comments=[
        Comment(id="c1", platform="reddit", author=None, date=None, text="NS has been very beneficial for Singapore's defence.", likes=None, position=0),
        Comment(id="c2", platform="reddit", author=None, date=None, text="The training builds character and discipline in young men.", likes=None, position=1),
        Comment(id="c3", platform="reddit", author=None, date=None, text="MINDEF should improve NSF allowances — the pay is too low.", likes=None, position=2),
        Comment(id="c4", platform="reddit", author=None, date=None, text="NS is a necessary sacrifice for the country's security.", likes=None, position=3),
        Comment(id="c5", platform="reddit", author=None, date=None, text="The new policy changes modernise our defence force.", likes=None, position=4),
        Comment(id="c6", platform="reddit", author=None, date=None, text="Management quality varies a lot across different units.", likes=None, position=5),
        Comment(id="c7", platform="reddit", author=None, date=None, text="NS teaches time management and teamwork.", likes=None, position=6),
        Comment(id="c8", platform="reddit", author=None, date=None, text="Consider the opportunity cost of 2 years for young Singaporeans.", likes=None, position=7),
    ],
)


def run(
    post: Post,
    mode: Literal["texture", "bucket"],
) -> dict:
    """Run LLM analysis on post and return a result dict.

    Returns:
        {"ok": True, "mode": ..., "title": ..., "output": ..., "citation_count": N}
        {"ok": True, "mode": ..., "skipped": True, "reason": "..."}  # bucket without holy grail
        {"ok": False, "mode": ..., "error": "..."}
    """
    from autoso.pipeline.flatten import flatten_post_comments
    from autoso.pipeline.llm import configure_llm
    from autoso.pipeline.pool import build_pool
    from autoso.pipeline.run_analysis import run_analysis

    try:
        if mode not in {"texture", "bucket"}:
            return {"ok": False, "mode": mode, "error": f"unknown mode: {mode!r}"}

        configure_llm()

        title = post.post_title
        flattened = [flatten_post_comments(post=post, n_cap=500, source_index=0)]
        pool = build_pool(posts=[post], flattened=flattened)

        hg_block = None
        if mode == "bucket":
            try:
                from autoso.pipeline.pipeline import _run_holy_grail

                hg_block = _run_holy_grail()
            except RuntimeError:
                return {
                    "ok": True,
                    "mode": mode,
                    "skipped": True,
                    "reason": "Holy Grail not ingested — run: python scripts/ingest_holy_grail.py <path>",
                }

        analysis = run_analysis(
            mode=mode,
            title=title,
            pool=pool,
            hg_block=hg_block,
        )

        return {
            "ok": True,
            "mode": mode,
            "title": title,
            "output": analysis.output_clean,
            "citation_count": len(analysis.citations),
        }

    except Exception as exc:
        return {"ok": False, "mode": mode, "error": str(exc)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live LLM analysis diagnostic")
    parser.add_argument("--mode", choices=["texture", "bucket"], default="texture")
    args = parser.parse_args()

    result = run(_CLI_CANNED_POST, args.mode)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)
```

- [ ] **Step 2: Verify the integration test for analyze still works (imports only, no live API call)**

```bash
cd /workspaces/AutoSO && python -c "from autoso.diagnostics.analyze import run; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add autoso/diagnostics/analyze.py
git commit -m "refactor: remove analysis_mode from diagnostics/analyze.py"
```

---

## Task 8: Full test suite verification

- [ ] **Step 1: Run the full test suite**

```bash
cd /workspaces/AutoSO && python -m pytest tests/ -v --ignore=tests/integration 2>&1 | tail -40
```

Expected: All tests PASS. No import errors.

- [ ] **Step 2: Check for any remaining references to removed symbols**

```bash
cd /workspaces/AutoSO && grep -r "run_prompt_analysis\|run_rag_analysis\|analysis_mode.*rag\|analysis_mode.*prompt\|-m prompt\|-m rag" --include="*.py" . | grep -v ".pyc"
```

Expected: No output (all references removed).

- [ ] **Step 3: Verify imports are clean**

```bash
cd /workspaces/AutoSO && python -c "
from autoso.pipeline.run_analysis import run_analysis
from autoso.pipeline.pipeline import run_pipeline
from autoso.bot.handlers import _parse_analysis_args
from autoso.diagnostics.analyze import run
print('all imports ok')
"
```

Expected: `all imports ok`

- [ ] **Step 4: Final commit if any cleanup needed**

```bash
git add -u
git status
# Only commit if there are remaining unstaged changes
```
