# AutoSO — Phase 1c: Citation UI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a NotebookLM-style side-by-side web UI where ASOs/SOs can read Textures/Buckets output with clickable `[N]` citation numbers that highlight the corresponding source comment in the right panel.

**Architecture:** FastAPI app with Jinja2 templates. One route: `GET /{run_id}`. Reads `analyses` + `citations` from Supabase. Left panel renders `output_cited` with `[N]` markers as clickable spans. Right panel lists source comments; clicking a `[N]` on the left scrolls to and highlights the matching comment on the right. Vanilla JS only — no framework.

**Tech Stack:** FastAPI, Uvicorn, Jinja2 (already in requirements), Supabase Python client (existing), pytest + httpx for route tests

**Pre-requisite:** Phase 1b complete. `migrations/001_initial_schema.sql` applied (includes `output_cited` column). `autoso/storage/supabase.py` exists.

---

## File Map

| File | Responsibility |
|------|---------------|
| `autoso/ui/__init__.py` | Empty |
| `autoso/ui/app.py` | FastAPI app, routes, Supabase queries |
| `autoso/ui/templates/citation.html` | Side-by-side UI layout |
| `autoso/ui/static/citation.css` | Panel layout styles |
| `autoso/ui/static/citation.js` | Citation click / highlight logic |
| `tests/test_ui/__init__.py` | Empty |
| `tests/test_ui/test_app.py` | Route tests using httpx + TestClient |

---

## Task 1: FastAPI App Scaffold

**Files:**
- Create: `autoso/ui/__init__.py`
- Create: `autoso/ui/app.py`

- [ ] **Step 1: Create directories and `__init__.py`**

```bash
mkdir -p autoso/ui/templates autoso/ui/static tests/test_ui
touch autoso/ui/__init__.py tests/test_ui/__init__.py
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_ui/test_app.py
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


def _mock_supabase(analysis: dict, citations: list[dict]):
    """Return a mock Supabase client that returns the given data.

    IMPORTANT: The two query chains (.table("analyses")... and .table("citations")...)
    share the same MagicMock return_value because MagicMock always returns the same
    child mock for the same attribute. This works here because the test only asserts
    on the final HTML output, not on individual Supabase calls. The citations chain
    has .order() which the analyses chain doesn't, so the mock routing diverges at
    that point — but the .single() call on analyses and the .order() call on citations
    both ultimately resolve to the same mock tree. If tests become flaky, switch to
    side_effect dispatch keyed on table name.
    """
    client = MagicMock()

    # analyses query chain: .table().select().eq().single().execute()
    analysis_result = MagicMock()
    analysis_result.data = analysis
    (
        client.table.return_value
        .select.return_value
        .eq.return_value
        .single.return_value
        .execute.return_value
    ) = analysis_result

    # citations query chain: .table().select().eq().order().execute()
    citations_result = MagicMock()
    citations_result.data = citations
    (
        client.table.return_value
        .select.return_value
        .eq.return_value
        .order.return_value
        .execute.return_value
    ) = citations_result

    return client


_SAMPLE_ANALYSIS = {
    "id": "abc-123",
    "url": "https://reddit.com/r/sg/comments/abc",
    "mode": "texture",
    "title": "NS Training",
    "output": "- 50% praised SAF",
    "output_cited": "- 50% praised SAF [1]",
    "created_at": "2026-04-15T10:00:00Z",
}

_SAMPLE_CITATIONS = [
    {
        "id": "cit-1",
        "run_id": "abc-123",
        "citation_number": 1,
        "text": "SAF soldiers were impressive",
        "platform": "reddit",
        "comment_id": "c1",
        "position": 0,
    }
]


def test_citation_view_returns_200():
    with patch("autoso.ui.app.create_client") as mock_cc:
        mock_cc.return_value = _mock_supabase(_SAMPLE_ANALYSIS, _SAMPLE_CITATIONS)
        from autoso.ui.app import app
        client = TestClient(app)
        response = client.get("/abc-123")
    assert response.status_code == 200


def test_citation_view_contains_title():
    with patch("autoso.ui.app.create_client") as mock_cc:
        mock_cc.return_value = _mock_supabase(_SAMPLE_ANALYSIS, _SAMPLE_CITATIONS)
        from autoso.ui.app import app
        client = TestClient(app)
        response = client.get("/abc-123")
    assert "NS Training" in response.text


def test_citation_view_contains_output_cited():
    with patch("autoso.ui.app.create_client") as mock_cc:
        mock_cc.return_value = _mock_supabase(_SAMPLE_ANALYSIS, _SAMPLE_CITATIONS)
        from autoso.ui.app import app
        client = TestClient(app)
        response = client.get("/abc-123")
    # [1] should appear in the HTML as a clickable span, not raw text
    assert "citation-ref" in response.text or "[1]" in response.text


def test_citation_view_contains_source_comment():
    with patch("autoso.ui.app.create_client") as mock_cc:
        mock_cc.return_value = _mock_supabase(_SAMPLE_ANALYSIS, _SAMPLE_CITATIONS)
        from autoso.ui.app import app
        client = TestClient(app)
        response = client.get("/abc-123")
    assert "SAF soldiers were impressive" in response.text


def test_citation_view_404_on_missing_run():
    with patch("autoso.ui.app.create_client") as mock_cc:
        client_mock = MagicMock()
        client_mock.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = Exception("not found")
        mock_cc.return_value = client_mock
        from autoso.ui.app import app
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/nonexistent-run-id")
    assert response.status_code == 404
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_ui/test_app.py -v
```

Expected: `ImportError` — `autoso.ui.app` does not exist.

- [ ] **Step 4: Create `autoso/ui/app.py`**

```python
# autoso/ui/app.py
import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from supabase import create_client
import autoso.config as config

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="AutoSO Citation UI")
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


def _get_client():
    return create_client(config.SUPABASE_URL, config.SUPABASE_KEY)


@app.get("/{run_id}", response_class=HTMLResponse)
async def citation_view(request: Request, run_id: str):
    client = _get_client()
    try:
        analysis_resp = (
            client.table("analyses")
            .select("*")
            .eq("id", run_id)
            .single()
            .execute()
        )
        analysis = analysis_resp.data
    except Exception:
        raise HTTPException(status_code=404, detail="Analysis not found")

    citations_resp = (
        client.table("citations")
        .select("*")
        .eq("run_id", run_id)
        .order("citation_number")
        .execute()
    )
    citations = citations_resp.data

    return templates.TemplateResponse(
        "citation.html",
        {
            "request": request,
            "analysis": analysis,
            "citations": citations,
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("autoso.ui.app:app", host="0.0.0.0", port=8000, reload=True)
```

- [ ] **Step 5: Run tests — they will fail on missing template**

```bash
pytest tests/test_ui/test_app.py::test_citation_view_returns_200 -v
```

Expected: 500 error or Jinja2 `TemplateNotFound`. Proceed to Task 2.

---

## Task 2: HTML Template

**Files:**
- Create: `autoso/ui/templates/citation.html`

- [ ] **Step 1: Create `autoso/ui/templates/citation.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{{ analysis.title }} — AutoSO</title>
  <link rel="stylesheet" href="/static/citation.css" />
</head>
<body>
  <header class="header">
    <h1>{{ analysis.title }}</h1>
    <span class="mode-badge mode-{{ analysis.mode }}">{{ analysis.mode | upper }}</span>
    <a class="source-link" href="{{ analysis.url }}" target="_blank" rel="noopener">View Source</a>
  </header>

  <main class="panels">
    <!-- LEFT PANEL: Analysis output with clickable [N] markers -->
    <section class="panel panel-output" id="panel-output">
      <h2 class="panel-heading">Analysis</h2>
      <div class="output-text" id="output-text">
        {{ analysis.output_cited | render_citations | safe }}
      </div>
    </section>

    <!-- RIGHT PANEL: Source comments -->
    <section class="panel panel-sources" id="panel-sources">
      <h2 class="panel-heading">Sources</h2>
      {% if citations %}
        {% for c in citations %}
        <article class="citation-card" id="citation-{{ c.citation_number }}">
          <header class="citation-card-header">
            <span class="citation-number">[{{ c.citation_number }}]</span>
            <span class="platform-badge platform-{{ c.platform }}">{{ c.platform }}</span>
            <span class="position-label">Comment #{{ c.position }}</span>
          </header>
          <p class="citation-text">{{ c.text }}</p>
        </article>
        {% endfor %}
      {% else %}
        <p class="no-citations">No citations available for this analysis.</p>
      {% endif %}
    </section>
  </main>

  <script src="/static/citation.js"></script>
</body>
</html>
```

- [ ] **Step 2: Register `render_citations` Jinja2 filter in `app.py`**

Add this to `autoso/ui/app.py` after the `templates = Jinja2Templates(...)` line:

```python
import re as _re


def _render_citations(text: str) -> str:
    """Convert [N] markers in output_cited to clickable <span> elements.

    HTML-escapes the text first to prevent XSS from LLM-generated content,
    then converts newlines and citation markers to HTML.
    """
    if not text:
        return ""
    from markupsafe import escape
    text = str(escape(text))
    text = text.replace("\n", "<br>\n")
    text = _re.sub(
        r"\[(\d+)\]",
        r'<span class="citation-ref" data-citation="\1" onclick="highlightCitation(\1)">[\1]</span>',
        text,
    )
    return text


templates.env.filters["render_citations"] = _render_citations
```

The final `app.py` with the filter inserted looks like:

```python
# autoso/ui/app.py
import logging
import re as _re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from supabase import create_client

import autoso.config as config

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="AutoSO Citation UI")
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _render_citations(text: str) -> str:
    """Convert [N] citation markers to clickable <span> elements.

    IMPORTANT: HTML-escape the text FIRST to prevent XSS from LLM output,
    then convert [N] markers and newlines. The `| safe` filter in the
    template trusts this function's output — we must earn that trust.
    """
    if not text:
        return ""
    from markupsafe import escape
    text = str(escape(text))
    text = text.replace("\n", "<br>\n")
    text = _re.sub(
        r"\[(\d+)\]",
        r'<span class="citation-ref" data-citation="\1" onclick="highlightCitation(\1)">[\1]</span>',
        text,
    )
    return text


templates.env.filters["render_citations"] = _render_citations

if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


def _get_client():
    return create_client(config.SUPABASE_URL, config.SUPABASE_KEY)


@app.get("/{run_id}", response_class=HTMLResponse)
async def citation_view(request: Request, run_id: str):
    client = _get_client()
    try:
        analysis_resp = (
            client.table("analyses")
            .select("*")
            .eq("id", run_id)
            .single()
            .execute()
        )
        analysis = analysis_resp.data
    except Exception:
        raise HTTPException(status_code=404, detail="Analysis not found")

    citations_resp = (
        client.table("citations")
        .select("*")
        .eq("run_id", run_id)
        .order("citation_number")
        .execute()
    )
    citations = citations_resp.data

    return templates.TemplateResponse(
        "citation.html",
        {
            "request": request,
            "analysis": analysis,
            "citations": citations,
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("autoso.ui.app:app", host="0.0.0.0", port=8000, reload=True)
```

- [ ] **Step 3: Run tests to verify they pass**

```bash
pytest tests/test_ui/test_app.py -v
```

Expected: 5 passed.

- [ ] **Step 4: Commit**

```bash
git add autoso/ui/__init__.py autoso/ui/app.py autoso/ui/templates/citation.html \
        tests/test_ui/__init__.py tests/test_ui/test_app.py
git commit -m "feat: add Citation UI FastAPI app and HTML template"
```

---

## Task 3: CSS + JavaScript

**Files:**
- Create: `autoso/ui/static/citation.css`
- Create: `autoso/ui/static/citation.js`

No unit tests for static assets — verified manually in the browser.

- [ ] **Step 1: Create `autoso/ui/static/citation.css`**

```css
/* autoso/ui/static/citation.css */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 14px;
  line-height: 1.6;
  background: #f5f5f5;
  color: #1a1a1a;
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  background: #fff;
  border-bottom: 1px solid #ddd;
  flex-shrink: 0;
}

.header h1 { font-size: 16px; font-weight: 600; }

.mode-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 999px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.mode-texture { background: #dbeafe; color: #1d4ed8; }
.mode-bucket  { background: #dcfce7; color: #15803d; }

.source-link {
  margin-left: auto;
  font-size: 12px;
  color: #6b7280;
  text-decoration: none;
}
.source-link:hover { text-decoration: underline; }

.panels {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0;
  flex: 1;
  overflow: hidden;
}

.panel {
  overflow-y: auto;
  padding: 20px;
}

.panel-output  { border-right: 1px solid #ddd; background: #fff; }
.panel-sources { background: #fafafa; }

.panel-heading {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #6b7280;
  margin-bottom: 16px;
}

/* Output text */
.output-text { white-space: pre-wrap; line-height: 1.8; }

.citation-ref {
  display: inline-block;
  background: #eff6ff;
  color: #2563eb;
  border-radius: 3px;
  padding: 0 3px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  user-select: none;
  transition: background 0.15s;
}
.citation-ref:hover        { background: #dbeafe; }
.citation-ref.active       { background: #2563eb; color: #fff; }

/* Citation cards */
.citation-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 10px;
  transition: border-color 0.2s, box-shadow 0.2s;
  scroll-margin-top: 20px;
}
.citation-card.highlighted {
  border-color: #2563eb;
  box-shadow: 0 0 0 2px #bfdbfe;
}

.citation-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.citation-number {
  font-weight: 700;
  font-size: 12px;
  color: #2563eb;
}

.platform-badge {
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 999px;
  font-weight: 600;
}
.platform-reddit    { background: #fff7ed; color: #c2410c; }
.platform-instagram { background: #fdf4ff; color: #7e22ce; }
.platform-facebook  { background: #eff6ff; color: #1d4ed8; }

.position-label { font-size: 11px; color: #9ca3af; }

.citation-text { font-size: 13px; color: #374151; line-height: 1.5; }

.no-citations { color: #9ca3af; font-style: italic; }
```

- [ ] **Step 2: Create `autoso/ui/static/citation.js`**

```javascript
// autoso/ui/static/citation.js

let _activeRef = null;
let _activeCard = null;

/**
 * Highlight a citation card in the right panel and mark the clicked [N] span.
 * @param {number} citationNumber
 */
function highlightCitation(citationNumber) {
  // Deactivate previous
  if (_activeRef)  _activeRef.classList.remove("active");
  if (_activeCard) _activeCard.classList.remove("highlighted");

  // Activate new citation ref span(s)
  const refs = document.querySelectorAll(
    `.citation-ref[data-citation="${citationNumber}"]`
  );
  refs.forEach(ref => ref.classList.add("active"));
  _activeRef = refs[0] || null;

  // Activate and scroll to citation card
  const card = document.getElementById(`citation-${citationNumber}`);
  if (card) {
    card.classList.add("highlighted");
    card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    _activeCard = card;
  }
}

// Keyboard: Escape deselects
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (_activeRef)  _activeRef.classList.remove("active");
    if (_activeCard) _activeCard.classList.remove("highlighted");
    _activeRef = null;
    _activeCard = null;
  }
});
```

- [ ] **Step 3: Commit**

```bash
git add autoso/ui/static/citation.css autoso/ui/static/citation.js
git commit -m "feat: add Citation UI CSS layout and citation click JS"
```

---

## Task 4: Manual Browser Verification

This task has no automated tests — it requires a real analysis run in Supabase.

- [ ] **Step 1: Start the UI server**

```bash
python -m autoso.ui.app
```

Expected: Uvicorn starts on `http://0.0.0.0:8000`.

- [ ] **Step 2: Open a run in the browser**

Navigate to `http://localhost:8000/<run_id>` (use a `run_id` from the `analyses` table in Supabase).

Expected:
- Two panels side by side
- Left panel: analysis output with blue `[N]` markers
- Right panel: source comments as cards with platform badges

- [ ] **Step 3: Click a citation**

Click any `[1]` marker in the left panel.

Expected:
- Clicked `[1]` turns solid blue
- Right panel scrolls to and highlights the matching citation card with a blue border

- [ ] **Step 4: Press Escape**

Expected: Highlight and active state both clear.

- [ ] **Step 5: Commit smoke test result**

If all visual checks pass:

```bash
git commit --allow-empty -m "test: Phase 1c Citation UI manual browser verification passed"
```
