# tests/test_ui/test_app.py
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


def _mock_supabase(analysis: dict, citations: list[dict]):
    client = MagicMock()

    analysis_result = MagicMock()
    analysis_result.data = analysis
    (
        client.table.return_value
        .select.return_value
        .eq.return_value
        .single.return_value
        .execute.return_value
    ) = analysis_result

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
