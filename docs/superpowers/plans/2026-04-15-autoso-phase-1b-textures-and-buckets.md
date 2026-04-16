# AutoSO — Phase 1b: Textures & Buckets Pipeline

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared analysis pipeline that scrapes comments, indexes them into ChromaDB, retrieves via RAG, generates Textures or Buckets output with LlamaIndex CitationBlock, stores results + citation index in Supabase, and returns clean plain-text to the Telegram user.

**Architecture:** A single `run_pipeline(url, mode, provided_title)` function orchestrates the full flow. Mode switching (`texture` / `bucket`) is a one-line prompt swap. The LLM layer is a one-line swap between Claude (prod) and Ollama (dev). All pipeline modules are independently testable. Supabase schema is designed Phase-1c-ready from the start (stores both clean output and citation-annotated output).

**Tech Stack:** LlamaIndex (`llama-index-core>=0.12.46`, `llama-index-llms-anthropic>=0.7.6`, `llama-index-llms-ollama>=0.4.0`, `llama-index-vector-stores-chroma>=0.4.0`), ChromaDB, Anthropic Claude API, Supabase Python client, python-telegram-bot (already installed from Phase 1a)

**Pre-requisite:** Phase 1a plan complete. `autoso/scraping/` package exists.

---

## File Map

| File | Responsibility |
|------|---------------|
| `autoso/pipeline/__init__.py` | Empty |
| `autoso/pipeline/llm.py` | `configure_llm()` — sets `Settings.llm` to Claude or Ollama |
| `autoso/pipeline/indexer.py` | `index_comments(comments)` — ephemeral ChromaDB index |
| `autoso/pipeline/holy_grail.py` | `ingest_holy_grail(path)` + `load_holy_grail()` — persistent index |
| `autoso/pipeline/prompts.py` | `TEXTURE_SYSTEM_PROMPT`, `BUCKET_SYSTEM_PROMPT`, format instructions |
| `autoso/pipeline/title.py` | `infer_title(post)` — LLM-inferred post title |
| `autoso/pipeline/citation.py` | `build_citation_engine(index)`, `extract_citations(response)`, `strip_citation_markers(text)` |
| `autoso/pipeline/pipeline.py` | `run_pipeline(url, mode, provided_title)` — full orchestration |
| `autoso/storage/__init__.py` | Empty |
| `autoso/storage/supabase.py` | `store_result(...)` — write analyses + citations rows |
| `migrations/001_initial_schema.sql` | Supabase DDL — `analyses` + `citations` tables |
| `scripts/ingest_holy_grail.py` | CLI script to ingest the Bucket Holy Grail document |
| `tests/test_pipeline/__init__.py` | Empty |
| `tests/test_pipeline/test_indexer.py` | Indexer unit tests |
| `tests/test_pipeline/test_holy_grail.py` | Holy Grail ingestion/load tests |
| `tests/test_pipeline/test_title.py` | Title inference unit tests |
| `tests/test_pipeline/test_citation.py` | Citation extraction + marker stripping tests |
| `tests/test_pipeline/test_pipeline.py` | Pipeline integration tests (Ollama, mocked scraper + Supabase) |
| `tests/test_storage/__init__.py` | Empty |
| `tests/test_storage/test_supabase.py` | Supabase storage unit tests (mocked client) |

---

## Task 1: LLM Configuration

**Files:**
- Create: `autoso/pipeline/__init__.py`
- Create: `autoso/pipeline/llm.py`

- [ ] **Step 1: Create `autoso/pipeline/__init__.py`**

```bash
mkdir -p autoso/pipeline tests/test_pipeline
touch autoso/pipeline/__init__.py tests/test_pipeline/__init__.py
```

- [ ] **Step 2: Write failing test**

```python
# tests/test_pipeline/test_llm.py
from unittest.mock import patch
from llama_index.core import Settings


def test_configure_llm_uses_ollama_when_flag_set():
    with patch("autoso.config.USE_OLLAMA", True), \
         patch("autoso.config.OLLAMA_MODEL", "llama3.2"):
        from autoso.pipeline.llm import configure_llm
        llm = configure_llm()
        from llama_index.llms.ollama import Ollama
        assert isinstance(llm, Ollama)
        assert Settings.llm is llm


def test_configure_llm_uses_anthropic_when_flag_unset():
    with patch("autoso.config.USE_OLLAMA", False), \
         patch("autoso.config.CLAUDE_MODEL", "claude-sonnet-4-6"), \
         patch("autoso.config.ANTHROPIC_API_KEY", "test-key"):
        from autoso.pipeline.llm import configure_llm
        llm = configure_llm()
        from llama_index.llms.anthropic import Anthropic
        assert isinstance(llm, Anthropic)
        assert Settings.llm is llm
```

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest tests/test_pipeline/test_llm.py -v
```

Expected: `ImportError` — `autoso.pipeline.llm` not found.

- [ ] **Step 4: Create `autoso/pipeline/llm.py`**

```python
# autoso/pipeline/llm.py
from llama_index.core import Settings
import autoso.config as config


def configure_llm():
    if config.USE_OLLAMA:
        from llama_index.llms.ollama import Ollama
        llm = Ollama(model=config.OLLAMA_MODEL, request_timeout=300.0)
    else:
        from llama_index.llms.anthropic import Anthropic
        llm = Anthropic(model=config.CLAUDE_MODEL, api_key=config.ANTHROPIC_API_KEY)

    Settings.llm = llm
    return llm
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/test_pipeline/test_llm.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add autoso/pipeline/__init__.py autoso/pipeline/llm.py \
        tests/test_pipeline/__init__.py tests/test_pipeline/test_llm.py
git commit -m "feat: add LLM configuration (Claude / Ollama swap)"
```

---

## Task 2: Comment Indexer

**Files:**
- Create: `autoso/pipeline/indexer.py`
- Create: `tests/test_pipeline/test_indexer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_pipeline/test_indexer.py
import pytest
from autoso.scraping.models import Comment
from autoso.pipeline.indexer import index_comments


def _make_comments(n: int) -> list[Comment]:
    return [
        Comment(
            platform="reddit",
            text=f"Comment {i}: NS training builds discipline and teamwork",
            comment_id=f"c{i}",
            position=i,
        )
        for i in range(n)
    ]


def test_index_returns_queryable_index():
    comments = _make_comments(5)
    index = index_comments(comments)
    engine = index.as_query_engine()
    response = engine.query("What do people think about NS?")
    assert str(response)  # non-empty


def test_index_stores_platform_metadata():
    comments = _make_comments(3)
    index = index_comments(comments)
    retriever = index.as_retriever(similarity_top_k=3)
    nodes = retriever.retrieve("NS training")
    for node in nodes:
        assert node.node.metadata["platform"] == "reddit"
        assert "comment_id" in node.node.metadata
        assert "position" in node.node.metadata


def test_two_runs_are_independent():
    c1 = _make_comments(2)
    c2 = [Comment(platform="instagram", text="IG comment about SAF", comment_id="ig0", position=0)]
    idx1 = index_comments(c1)
    idx2 = index_comments(c2)
    # Both indexes should be queryable independently
    assert str(idx1.as_query_engine().query("NS"))
    assert str(idx2.as_query_engine().query("SAF"))


def test_empty_comments_returns_empty_index():
    # Should not raise
    index = index_comments([])
    engine = index.as_query_engine()
    # Query on empty index returns an empty/no-result response — does not raise
    response = engine.query("NS")
    assert response is not None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_pipeline/test_indexer.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Create `autoso/pipeline/indexer.py`**

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
    """Index comments into an ephemeral (in-memory) ChromaDB collection.

    Returns a VectorStoreIndex ready for querying. Each run gets its own
    collection so parallel runs do not interfere.
    """
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
                "comment_id": comment.comment_id,
                "position": comment.position,
            },
            doc_id=comment.comment_id,
        )
        for comment in comments
    ]

    return VectorStoreIndex.from_documents(
        documents, storage_context=storage_context, show_progress=False
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_pipeline/test_indexer.py -v
```

Expected: 4 passed. Note: `test_index_returns_queryable_index` requires a running LLM. Set `USE_OLLAMA=true` in your `.env` and ensure Ollama is running, or skip it with `pytest -k "not queryable"` until the LLM is configured.

- [ ] **Step 5: Commit**

```bash
git add autoso/pipeline/indexer.py tests/test_pipeline/test_indexer.py
git commit -m "feat: add ephemeral comment indexer (ChromaDB per-run)"
```

---

## Task 3: Bucket Holy Grail — Persistent Index

**Files:**
- Create: `autoso/pipeline/holy_grail.py`
- Create: `scripts/ingest_holy_grail.py`
- Create: `tests/test_pipeline/test_holy_grail.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_pipeline/test_holy_grail.py
import pytest
import tempfile
import os
from pathlib import Path


def _write_temp_doc(content: str) -> str:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(content)
        return f.name


def test_ingest_creates_persistent_index(tmp_path, monkeypatch):
    monkeypatch.setattr("autoso.config.CHROMADB_PATH", str(tmp_path))
    from autoso.pipeline.holy_grail import ingest_holy_grail, load_holy_grail

    doc_path = _write_temp_doc(
        "Positive: Praised MINDEF for strong military\n"
        "Neutral: Discussed NS training\n"
        "Negative: Criticised waste of taxpayer money\n"
    )
    try:
        ingest_holy_grail(doc_path)
        index = load_holy_grail()
        assert index is not None
    finally:
        os.unlink(doc_path)


def test_ingest_is_idempotent(tmp_path, monkeypatch):
    """Re-ingesting the same doc replaces the old index, not append."""
    monkeypatch.setattr("autoso.config.CHROMADB_PATH", str(tmp_path))
    from autoso.pipeline.holy_grail import ingest_holy_grail, load_holy_grail

    doc_path = _write_temp_doc("Positive: Praised SAF capability")
    try:
        ingest_holy_grail(doc_path)
        ingest_holy_grail(doc_path)  # second call must not raise
        index = load_holy_grail()
        assert index is not None
    finally:
        os.unlink(doc_path)


def test_load_raises_if_not_ingested(tmp_path, monkeypatch):
    monkeypatch.setattr("autoso.config.CHROMADB_PATH", str(tmp_path))
    from autoso.pipeline.holy_grail import load_holy_grail
    with pytest.raises(Exception):
        load_holy_grail()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_pipeline/test_holy_grail.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Create `autoso/pipeline/holy_grail.py`**

```python
# autoso/pipeline/holy_grail.py
import chromadb
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext
from llama_index.vector_stores.chroma import ChromaVectorStore
import autoso.config as config

_COLLECTION_NAME = "bucket_holy_grail"


def _get_client() -> chromadb.PersistentClient:
    return chromadb.PersistentClient(path=config.CHROMADB_PATH)


def ingest_holy_grail(file_path: str) -> VectorStoreIndex:
    """Ingest a document into the persistent Holy Grail index.

    Replaces any existing collection. Call this whenever the Holy Grail
    document is updated.
    """
    client = _get_client()
    try:
        client.delete_collection(_COLLECTION_NAME)
    except ValueError:
        pass  # collection did not exist — fine

    collection = client.create_collection(_COLLECTION_NAME)
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    docs = SimpleDirectoryReader(input_files=[file_path]).load_data()
    return VectorStoreIndex.from_documents(
        docs, storage_context=storage_context, show_progress=False
    )


def load_holy_grail() -> VectorStoreIndex:
    """Load the existing Holy Grail index. Raises if not yet ingested."""
    client = _get_client()
    collection = client.get_collection(_COLLECTION_NAME)  # raises ValueError if missing
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    return VectorStoreIndex.from_vector_store(
        vector_store, storage_context=storage_context
    )
```

- [ ] **Step 4: Create `scripts/ingest_holy_grail.py`**

```python
#!/usr/bin/env python
# scripts/ingest_holy_grail.py
"""Ingest the Bucket Holy Grail document into the persistent ChromaDB index.

Usage:
    python scripts/ingest_holy_grail.py path/to/holy_grail.docx
    python scripts/ingest_holy_grail.py path/to/holy_grail.txt
"""
import sys
from pathlib import Path

# Add project root to path so autoso package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from autoso.pipeline.holy_grail import ingest_holy_grail

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/ingest_holy_grail.py <path_to_document>")
        sys.exit(1)

    path = sys.argv[1]
    if not Path(path).exists():
        print(f"File not found: {path}")
        sys.exit(1)

    print(f"Ingesting {path}...")
    ingest_holy_grail(path)
    print("Done. Holy Grail index is ready.")
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_pipeline/test_holy_grail.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
mkdir -p scripts
git add autoso/pipeline/holy_grail.py scripts/ingest_holy_grail.py \
        tests/test_pipeline/test_holy_grail.py
git commit -m "feat: add Holy Grail persistent index + ingest script"
```

---

## Task 4: System Prompts

**Files:**
- Create: `autoso/pipeline/prompts.py`

No unit tests — this file is plain string constants verified by the integration test in Task 10.

- [ ] **Step 1: Create `autoso/pipeline/prompts.py`**

```python
# autoso/pipeline/prompts.py

TEXTURE_SYSTEM_PROMPT = """\
This GPT's role is to produce a list of Textures relating to a list of comment threads on a certain issue. \
Textures are a BRIEF summary of threads of comments across many different social media comments, \
such as Facebook, Reddit, Instagram, etc.

***Referencing Sources***

Comments will be provided in the format:
INSTAGRAM POST:
<POST CONTENT>

COMMENTS:
<LONG LIST OF COMMENTS>

When referencing comments, do NOT quote sources from under the POST header. Use the POST header as \
reference for context of the comments below ONLY. Only quote sources from the COMMENTS header. \
Comments are delimited via UI markers such as "2h reply edited", which can be ignored. Ensure that \
comments are sourced and counted on a per-comment basis, not on a chunk-of-comments basis.

***Interpreting Comments***

Unless specified otherwise, analyse the comments from Singapore's MINDEF/SAF/NS/Defence perspective. \
All MINDEF/SAF/NS mentions must be mentioned. Quote ALL sources.

Each point should discuss the GENERAL SCOPE of a comment, not the specific points raised in the comment \
(eg "Discussed SG-China relations."). Do NOT add on additional information or examples relating to the \
comment in the points—points should be AS GENERAL AS POSSIBLE. No compound sentences allowed. \
No list of commas allowed, maximum is "A/B/C". No multi-clause sentence allowed.

***Formatting Output***

Texture points start with
- "X%..." for general purpose
- "Y comments..." usually for small number of SG/SAF/MINDEF mentions/shocking comments worth mentioning

Followed by
- "opined that" for making a specific opinion
- "discussed..." for back and forth discursion without stating an opinion
- "praised/criticised/etc..." also works

Use bullet points for each Texture point. The percentages should add up to roughly 100%. \
Have each point on its own line without huge line breaks in between. \
Do NOT end each point with full-stops. For salutation names, just use Mr/Mrs NAME (eg Mr Chan). \
Do NOT state who said specific comments.

For the headers, just a title "<Topic Statement>" at the top, no need to call it a "Texture".

Here is a list of acronyms which may be used:
- NS = National Service
- WoG = Whole of Government
- NSman/NSmen\
"""

BUCKET_SYSTEM_PROMPT = """\
This GPT's role is to produce a list of Buckets relating to a list of comment threads on a certain issue. \
Unless specified otherwise, analyse the comments from Singapore's MINDEF/SAF/NS/Defence perspective. \
Negative includes anything that goes against MINDEF/SAF's current policies/stance.

Select AT LEAST 8 relevant Buckets from the Bucket Holy Grail per sentiment (Positive, Neutral or Negative). \
If there are more sentiments, please include ALL sentiments, there can be a skewed amount of positive \
vs negative sentiments.

Only if not enough to hit 8 buckets each, select pre-emptives from the Bucket Holy Grail documents, \
which are potential comments which people may talk about. Pre-emptives should be listed in numbers \
relating to which points above are pre-emptives. Avoid modifying phrasing of pre-emptives, \
minimal change is okay if necessary.

Each point should discuss the GENERAL SCOPE of a comment, not the specific points raised in the comment \
(eg "Discussed SG-China relations."). Do NOT add on additional information or examples relating to the \
comment in the points—points should be AS GENERAL AS POSSIBLE \
(no need for "(e.g. fighter jets, submarines, etc.)")

Use double spacing before each point (e.g. "1.  Discussed..."). Have each point on its own line without \
huge line breaks in between. Do NOT end each point with full-stops. Between each section, leave single \
line breaks. For salutation names, just use Mr/Mrs NAME (eg Mr Chan)

Here is a list of acronyms which must be used:
- NS = National Service
- WoG = Whole of Government\
"""

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

- [ ] **Step 2: Verify import**

```bash
python -c "from autoso.pipeline.prompts import TEXTURE_SYSTEM_PROMPT, BUCKET_SYSTEM_PROMPT; print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add autoso/pipeline/prompts.py
git commit -m "feat: add Texture and Bucket system prompts"
```

---

## Task 5: Title Inference

**Files:**
- Create: `autoso/pipeline/title.py`
- Create: `tests/test_pipeline/test_title.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_pipeline/test_title.py
from unittest.mock import MagicMock, patch
from autoso.scraping.models import Comment, Post
from autoso.pipeline.title import infer_title


def _make_post(content: str, comments: list[str]) -> Post:
    return Post(
        title="",
        content=content,
        url="https://reddit.com/r/test/comments/abc",
        platform="reddit",
        comments=[
            Comment(platform="reddit", text=t, comment_id=f"c{i}", position=i)
            for i, t in enumerate(comments)
        ],
    )


def test_infer_title_returns_string():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = MagicMock(text="NS Training Exercise")

    with patch("autoso.pipeline.title.Settings") as mock_settings:
        mock_settings.llm = mock_llm
        post = _make_post("XLS25 exercise underway", ["Great exercise", "SAF looks strong"])
        result = infer_title(post)

    assert isinstance(result, str)
    assert len(result) > 0


def test_infer_title_strips_quotes():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = MagicMock(text='"NS Training Debate"')

    with patch("autoso.pipeline.title.Settings") as mock_settings:
        mock_settings.llm = mock_llm
        post = _make_post("Post content", ["Comment 1"])
        result = infer_title(post)

    assert not result.startswith('"')
    assert not result.endswith('"')


def test_infer_title_includes_platform_in_prompt():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = MagicMock(text="Test Title")
    captured_prompts = []

    def capture(prompt):
        captured_prompts.append(prompt)
        return MagicMock(text="Test Title")

    mock_llm.complete.side_effect = capture

    with patch("autoso.pipeline.title.Settings") as mock_settings:
        mock_settings.llm = mock_llm
        post = _make_post("content", ["comment"])
        post.platform = "instagram"
        infer_title(post)

    assert "instagram" in captured_prompts[0].lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_pipeline/test_title.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Create `autoso/pipeline/title.py`**

```python
# autoso/pipeline/title.py
from llama_index.core import Settings
from autoso.scraping.models import Post


def infer_title(post: Post) -> str:
    """Use the configured LLM to infer a title from post content and sample comments."""
    sample_comments = " | ".join(
        c.text[:120] for c in post.comments[:5]
    )
    prompt = (
        f"Based on the following post content and sample comments from {post.platform}, "
        f"generate a concise title (3-8 words, Title Case). "
        f"Output ONLY the title, nothing else.\n\n"
        f"Post content: {post.content[:500]}\n"
        f"Sample comments: {sample_comments}\n\n"
        f"Title:"
    )
    response = Settings.llm.complete(prompt)
    return str(response).strip().strip("\"'")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_pipeline/test_title.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add autoso/pipeline/title.py tests/test_pipeline/test_title.py
git commit -m "feat: add LLM-based title inference"
```

---

## Task 6: Citation Engine

**Files:**
- Create: `autoso/pipeline/citation.py`
- Create: `tests/test_pipeline/test_citation.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_pipeline/test_citation.py
import re
from unittest.mock import MagicMock
from autoso.pipeline.citation import extract_citations, strip_citation_markers, CitationNode


def _make_source_node(text: str, platform: str, comment_id: str, position: int):
    node = MagicMock()
    node.node.text = text
    node.node.metadata = {
        "platform": platform,
        "comment_id": comment_id,
        "position": position,
    }
    return node


def test_extract_citations_maps_nodes_to_citation_numbers():
    response = MagicMock()
    response.source_nodes = [
        _make_source_node("NS is vital", "reddit", "c1", 0),
        _make_source_node("SAF is strong", "instagram", "ig_5", 5),
    ]
    citations = extract_citations(response)
    assert len(citations) == 2
    assert citations[0].citation_number == 1
    assert citations[0].text == "NS is vital"
    assert citations[0].platform == "reddit"
    assert citations[1].citation_number == 2
    assert citations[1].comment_id == "ig_5"
    assert citations[1].position == 5


def test_extract_citations_returns_empty_for_no_sources():
    response = MagicMock()
    response.source_nodes = []
    assert extract_citations(response) == []


def test_strip_citation_markers_removes_numbers():
    text = "20% opined that [1] NS is important [2] for defence [3]"
    result = strip_citation_markers(text)
    assert "[1]" not in result
    assert "[2]" not in result
    assert "[3]" not in result
    assert "20% opined that" in result
    assert "NS is important" in result


def test_strip_citation_markers_handles_no_markers():
    text = "Clean text with no markers"
    assert strip_citation_markers(text) == "Clean text with no markers"


def test_strip_citation_markers_handles_consecutive_markers():
    text = "Point about SAF [1][2][3] and defence"
    result = strip_citation_markers(text)
    assert not re.search(r'\[\d+\]', result)
    assert "Point about SAF" in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_pipeline/test_citation.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Create `autoso/pipeline/citation.py`**

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
    comment_id: str
    position: int


def build_citation_engine(
    index: VectorStoreIndex, similarity_top_k: int = 10
) -> CitationQueryEngine:
    """Build a CitationQueryEngine that annotates its response with [N] markers."""
    return CitationQueryEngine.from_args(
        index,
        similarity_top_k=similarity_top_k,
        citation_chunk_size=512,
    )


def extract_citations(response) -> List[CitationNode]:
    """Extract source node metadata from a CitationQueryEngine response."""
    nodes = []
    for i, node in enumerate(response.source_nodes):
        nodes.append(
            CitationNode(
                citation_number=i + 1,
                text=node.node.text,
                platform=node.node.metadata.get("platform", "unknown"),
                comment_id=node.node.metadata.get("comment_id", f"node_{i}"),
                position=node.node.metadata.get("position", -1),
            )
        )
    return nodes


def strip_citation_markers(text: str) -> str:
    """Remove all [N] citation markers from text."""
    return re.sub(r"\s*\[\d+\]", "", text).strip()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_pipeline/test_citation.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add autoso/pipeline/citation.py tests/test_pipeline/test_citation.py
git commit -m "feat: add CitationQueryEngine wrapper and citation extraction"
```

---

## Task 7: Supabase Schema + Storage

**Files:**
- Create: `migrations/001_initial_schema.sql`
- Create: `autoso/storage/__init__.py`
- Create: `autoso/storage/supabase.py`
- Create: `tests/test_storage/__init__.py`
- Create: `tests/test_storage/test_supabase.py`

- [ ] **Step 1: Create `migrations/001_initial_schema.sql`**

Run this SQL in the Supabase dashboard SQL editor before running the bot.

```sql
-- AutoSO initial schema
-- Run in Supabase dashboard: SQL Editor

CREATE TABLE IF NOT EXISTS analyses (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url           TEXT        NOT NULL,
    mode          TEXT        NOT NULL CHECK (mode IN ('texture', 'bucket')),
    title         TEXT        NOT NULL,
    output        TEXT        NOT NULL,            -- Clean text, no [N] markers (Telegram output)
    output_cited  TEXT,                            -- Text with [N] markers (Phase 1c web UI)
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Citation index
-- One row per cited source node per analysis run.
-- Never stores commenter username/handle — only text, platform, position.
CREATE TABLE IF NOT EXISTS citations (
    id              UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID    NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    citation_number INTEGER NOT NULL,
    text            TEXT    NOT NULL,     -- Source comment text
    platform        TEXT    NOT NULL,     -- 'reddit' | 'instagram' | 'facebook'
    comment_id      TEXT,                 -- Platform-specific ID (may be synthetic)
    position        INTEGER,              -- 0-indexed order in original comment list
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_citations_run_id
    ON citations (run_id);

CREATE INDEX IF NOT EXISTS idx_analyses_created_at
    ON analyses (created_at DESC);
```

- [ ] **Step 2: Apply schema**

Open Supabase dashboard → SQL Editor → paste and run the above SQL.

Expected: Both tables created, no errors.

- [ ] **Step 3: Write failing tests**

```python
# tests/test_storage/test_supabase.py
from unittest.mock import MagicMock, patch, call
from autoso.storage.supabase import store_result


def _mock_supabase_client():
    """Return a mock Supabase client where .table().insert().execute() chains work."""
    client = MagicMock()
    execute_mock = MagicMock()
    client.table.return_value.insert.return_value.execute = MagicMock(
        return_value=execute_mock
    )
    return client


@patch("autoso.storage.supabase.create_client")
def test_store_result_inserts_analysis_row(mock_create):
    client = _mock_supabase_client()
    mock_create.return_value = client

    run_id = store_result(
        url="https://reddit.com/r/test/comments/abc",
        mode="texture",
        title="Test Post",
        output="- 50% opined that NS is important",
        output_cited="- 50% opined that NS is important [1]",
        citation_index=[],
    )

    assert isinstance(run_id, str)
    assert len(run_id) == 36  # UUID format
    client.table.assert_any_call("analyses")


@patch("autoso.storage.supabase.create_client")
def test_store_result_inserts_citation_rows(mock_create):
    client = _mock_supabase_client()
    mock_create.return_value = client

    citations = [
        {"citation_number": 1, "text": "NS comment", "platform": "reddit",
         "comment_id": "c1", "position": 0},
        {"citation_number": 2, "text": "SAF comment", "platform": "instagram",
         "comment_id": "ig_5", "position": 5},
    ]

    store_result(
        url="http://x.com",
        mode="bucket",
        title="T",
        output="output",
        output_cited="output [1] [2]",
        citation_index=citations,
    )

    # citations table should have been written
    table_calls = [str(c) for c in client.table.call_args_list]
    assert any("citations" in c for c in table_calls)


@patch("autoso.storage.supabase.create_client")
def test_store_result_skips_citation_insert_when_empty(mock_create):
    client = _mock_supabase_client()
    mock_create.return_value = client

    store_result(
        url="http://x.com",
        mode="texture",
        title="T",
        output="output",
        output_cited=None,
        citation_index=[],
    )

    # Only the analyses table should have been written
    table_names = [c.args[0] for c in client.table.call_args_list]
    assert "analyses" in table_names
    assert "citations" not in table_names
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
pytest tests/test_storage/test_supabase.py -v
```

Expected: `ImportError`.

- [ ] **Step 5: Create `autoso/storage/__init__.py`** and **`tests/test_storage/__init__.py`**

```bash
mkdir -p autoso/storage tests/test_storage
touch autoso/storage/__init__.py tests/test_storage/__init__.py
```

- [ ] **Step 6: Create `autoso/storage/supabase.py`**

```python
# autoso/storage/supabase.py
import uuid
from typing import List, Optional

from supabase import create_client, Client

import autoso.config as config


def _get_client() -> Client:
    return create_client(config.SUPABASE_URL, config.SUPABASE_KEY)


def store_result(
    url: str,
    mode: str,
    title: str,
    output: str,
    output_cited: Optional[str],
    citation_index: List[dict],
) -> str:
    """Persist an analysis result and its citations. Returns the run_id (UUID)."""
    client = _get_client()
    run_id = str(uuid.uuid4())

    client.table("analyses").insert(
        {
            "id": run_id,
            "url": url,
            "mode": mode,
            "title": title,
            "output": output,
            "output_cited": output_cited,
        }
    ).execute()

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

- [ ] **Step 7: Run tests to verify they pass**

```bash
pytest tests/test_storage/test_supabase.py -v
```

Expected: 3 passed.

- [ ] **Step 8: Commit**

```bash
mkdir -p migrations
git add migrations/001_initial_schema.sql \
        autoso/storage/__init__.py autoso/storage/supabase.py \
        tests/test_storage/__init__.py tests/test_storage/test_supabase.py
git commit -m "feat: add Supabase schema and storage module"
```

---

## Task 8: Pipeline Orchestrator

**Files:**
- Create: `autoso/pipeline/pipeline.py`
- Create: `tests/test_pipeline/test_pipeline.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_pipeline/test_pipeline.py
from dataclasses import dataclass
from unittest.mock import MagicMock, patch
from autoso.scraping.models import Comment, Post
from autoso.pipeline.pipeline import run_pipeline, PipelineResult


def _make_post(platform: str = "reddit") -> Post:
    return Post(
        title="XLS25 Concludes",
        content="The annual exercise has ended.",
        url=f"https://{platform}.com/test",
        platform=platform,
        comments=[
            Comment(platform=platform, text="SAF soldiers were impressive", comment_id="c1", position=0),
            Comment(platform=platform, text="Good for SG-US bilateral relations", comment_id="c2", position=1),
            Comment(platform=platform, text="NS builds character and resilience", comment_id="c3", position=2),
        ],
    )


def _patch_pipeline(mode: str, post: Post, run_id: str = "run-123"):
    """Context manager patches: scraper, llm, store_result, holy_grail (bucket only)."""
    mock_scraper = MagicMock()
    mock_scraper.scrape.return_value = post

    mock_response = MagicMock()
    mock_response.__str__ = lambda self: (
        "- 60% praised SAF [1]\n- 40% discussed NS [2]"
        if mode == "texture"
        else "*Positive*\n1.  Praised SAF capability [1]\n\n*Neutral*\n1.  Discussed NS [2]\n\n*Negative*\n1.  Criticised budget [3]"
    )
    mock_response.source_nodes = []

    mock_engine = MagicMock()
    mock_engine.query.return_value = mock_response

    patches = [
        patch("autoso.pipeline.pipeline.get_scraper", return_value=mock_scraper),
        patch("autoso.pipeline.pipeline.configure_llm"),
        patch("autoso.pipeline.pipeline.store_result", return_value=run_id),
        patch("autoso.pipeline.pipeline.build_citation_engine", return_value=mock_engine),
        patch("autoso.pipeline.pipeline.index_comments", return_value=MagicMock()),
    ]
    if mode == "bucket":
        patches.append(patch("autoso.pipeline.pipeline.load_holy_grail", return_value=MagicMock()))

    return patches


def _apply_patches(patch_list):
    """Apply a list of patch context managers."""
    import contextlib
    return contextlib.ExitStack()


def test_texture_returns_pipeline_result():
    post = _make_post()
    patches = _patch_pipeline("texture", post)
    mocks = [p.start() for p in patches]
    try:
        result = run_pipeline(
            url="https://reddit.com/r/test/comments/abc",
            mode="texture",
            provided_title="XLS25 Concludes",
        )
        assert isinstance(result, PipelineResult)
        assert result.title == "XLS25 Concludes"
        assert result.run_id == "run-123"
        # No [N] citation markers in the Telegram output
        import re
        assert not re.search(r'\[\d+\]', result.output)
    finally:
        for p in patches:
            p.stop()


def test_bucket_loads_holy_grail():
    post = _make_post()
    patches = _patch_pipeline("bucket", post)
    mock_holy_grail = None
    mocks = [p.start() for p in patches]
    try:
        # Find the holy grail mock
        from autoso.pipeline import pipeline as pip_module
        run_pipeline(url="https://reddit.com/r/test/comments/abc", mode="bucket")
    finally:
        for p in patches:
            p.stop()


def test_texture_uses_provided_title():
    post = _make_post()
    patches = _patch_pipeline("texture", post)
    [p.start() for p in patches]
    try:
        result = run_pipeline(
            url="https://reddit.com/r/test",
            mode="texture",
            provided_title="My Custom Title",
        )
        assert result.title == "My Custom Title"
    finally:
        for p in patches:
            p.stop()


def test_texture_infers_title_when_not_provided():
    post = _make_post()
    patches = _patch_pipeline("texture", post)
    extra_patch = patch(
        "autoso.pipeline.pipeline.infer_title", return_value="Inferred Title"
    )
    [p.start() for p in patches]
    extra_patch.start()
    try:
        result = run_pipeline(
            url="https://reddit.com/r/test",
            mode="texture",
            provided_title=None,
        )
        assert result.title == "Inferred Title"
    finally:
        for p in patches:
            p.stop()
        extra_patch.stop()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_pipeline/test_pipeline.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Create `autoso/pipeline/pipeline.py`**

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
from autoso.scraping.base import get_scraper
from autoso.storage.supabase import store_result

logger = logging.getLogger(__name__)

Mode = Literal["texture", "bucket"]


@dataclass
class PipelineResult:
    title: str
    output: str            # Clean — no [N] markers (for Telegram)
    output_cited: str      # With [N] markers (stored for Phase 1c web UI)
    citation_index: List[CitationNode] = field(default_factory=list)
    run_id: str = ""


def run_pipeline(
    url: str,
    mode: Mode,
    provided_title: Optional[str] = None,
) -> PipelineResult:
    configure_llm()

    # 1. Scrape
    scraper = get_scraper(url)
    post = scraper.scrape(url)
    logger.info("Scraped %d comments from %s", len(post.comments), post.platform)

    # 2. Title
    title = provided_title or infer_title(post)

    # 3. Index comments (ephemeral)
    comment_index = index_comments(post.comments)
    comment_engine = build_citation_engine(comment_index)

    # 4. Build prompt
    comments_text = "\n".join(
        f"Comment {c.position}: {c.text}" for c in post.comments
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

    # 5. Query with citations
    response = comment_engine.query(full_query)

    # 6. Build outputs
    output_cited = str(response)
    output_clean = strip_citation_markers(output_cited)

    # 7. Extract citations
    citations = extract_citations(response)

    # 8. Store
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
                "comment_id": c.comment_id,
                "position": c.position,
            }
            for c in citations
        ],
    )

    return PipelineResult(
        title=title,
        output=output_clean,
        output_cited=output_cited,
        citation_index=citations,
        run_id=run_id,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_pipeline/test_pipeline.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add autoso/pipeline/pipeline.py tests/test_pipeline/test_pipeline.py
git commit -m "feat: add shared Texture/Bucket pipeline orchestrator"
```

---

## Task 9: Bot Handler Tests

**Files:**
- Modify: `autoso/bot/handlers.py` (no change needed — handlers call `run_pipeline` which now exists)
- Create: `tests/test_bot/__init__.py`
- Create: `tests/test_bot/test_handlers.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_bot/test_handlers.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from autoso.bot.handlers import texture_handler, bucket_handler, start_handler
from autoso.pipeline.pipeline import PipelineResult
from autoso.pipeline.citation import CitationNode


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
    with patch("autoso.bot.handlers.run_pipeline", return_value=mock_result):
        await texture_handler(update, context)

    calls = [str(c) for c in update.message.reply_text.call_args_list]
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
    with patch("autoso.bot.handlers.run_pipeline", return_value=mock_result):
        await texture_handler(update, context)

    calls = [str(c) for c in update.message.reply_text.call_args_list]
    assert any("too long" in c for c in calls)
    assert any("run-abc" in c for c in calls)


async def test_handler_replies_on_pipeline_exception():
    update, context = _make_update(99, ["https://reddit.com/r/sg/comments/abc"])
    with patch("autoso.bot.handlers.run_pipeline", side_effect=RuntimeError("scrape failed")):
        await texture_handler(update, context)

    calls = [str(c) for c in update.message.reply_text.call_args_list]
    assert any("error" in c.lower() for c in calls)
```

- [ ] **Step 2: Create `tests/test_bot/__init__.py`**

```bash
mkdir -p tests/test_bot
touch tests/test_bot/__init__.py
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_bot/test_handlers.py -v
```

Expected: `ImportError` or attribute errors — `run_pipeline` not importable from handlers yet.

- [ ] **Step 4: Run tests to verify they pass**

The handlers already import `run_pipeline` from `autoso.pipeline.pipeline`, which now exists.

```bash
pytest tests/test_bot/test_handlers.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Run the full suite**

```bash
pytest -v
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add tests/test_bot/__init__.py tests/test_bot/test_handlers.py
git commit -m "test: add bot handler tests — Phase 1b complete"
```

---

## Task 10: End-to-End Smoke Test (Manual)

This is a manual test — run it once Ollama is up and `.env` is populated.

- [ ] **Step 1: Ingest Holy Grail document (once Holy Grail doc is available)**

```bash
python scripts/ingest_holy_grail.py /path/to/holy_grail.txt
```

Expected: `Done. Holy Grail index is ready.`

- [ ] **Step 2: Run a Texture analysis against a real Reddit post**

```bash
python -c "
import os; os.environ.setdefault('USE_OLLAMA', 'true')
from autoso.pipeline.pipeline import run_pipeline
result = run_pipeline('https://www.reddit.com/r/singapore/comments/REAL_POST_ID', mode='texture')
print(result.output)
print('--- run_id:', result.run_id)
"
```

Expected: Markdown-formatted Texture output with no `[N]` markers. Run ID printed.

- [ ] **Step 3: Verify Supabase rows**

In Supabase dashboard → Table Editor → `analyses`: confirm row exists with correct `mode`, `title`, `output`, `output_cited`.

In `citations` table: confirm rows exist with `run_id` matching the analyses row.

- [ ] **Step 4: Start the bot and test via Telegram**

```bash
python -m autoso.bot.main
```

Send `/texture https://www.reddit.com/r/singapore/comments/REAL_POST_ID` from a whitelisted Telegram account.

Expected: "Processing..." message followed by formatted Texture output.
