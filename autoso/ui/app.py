# autoso/ui/app.py
import logging
import re as _re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from supabase import create_client

import autoso.config as config

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="AutoSO Citation UI")
_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)))


def _render_citations(text: str) -> str:
    """Convert [N] citation markers to clickable <span> elements.

    HTML-escapes the text FIRST to prevent XSS from LLM output,
    then converts [N] markers and newlines.
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


_env.filters["render_citations"] = _render_citations

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

    # Render template manually to avoid TemplateResponse caching issues
    template = _env.get_template("citation.html")
    context = {
        "request": request,
        "analysis": analysis,
        "citations": citations,
    }
    html_content = template.render(context)
    return HTMLResponse(content=html_content)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("autoso.ui.app:app", host="0.0.0.0", port=8000, reload=True)
