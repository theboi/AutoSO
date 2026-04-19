from unittest.mock import MagicMock, patch

from autoso.pipeline.analysis import AnalysisResult, CitationRecord
from autoso.storage.supabase import store_multi_result


def _fake_client():
    """A MagicMock supabase client whose table().insert().execute() returns .data rows."""
    client = MagicMock()

    def table(name):
        t = MagicMock()

        def insert(rows):
            chain = MagicMock()
            if name == "analysis_sources":
                payload = rows if isinstance(rows, list) else [rows]
                data = [{**r, "id": f"src-{i}"} for i, r in enumerate(payload)]
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

    citation_inserts = [rows for name, rows in insert_log if name == "citations"]
    assert citation_inserts, "citations insert did not happen"
    citation_row = citation_inserts[0][0]
    assert citation_row["citation_number"] == 2
    assert citation_row["comment_id"] == "b1"
    assert citation_row["position"] == 0
    assert citation_row["text"] == "bravo"
    assert citation_row["source_id"] == "src-1"

    analyses_inserts = [rows for name, rows in insert_log if name == "analyses"]
    assert analyses_inserts
    analysis_row = analyses_inserts[0][0]
    assert analysis_row["analysis_mode"] == "prompt"
    assert analysis_row["mode"] == "texture"
    assert analysis_row["title"] == "T"
    assert "url" not in analysis_row


def test_store_multi_result_raises_when_urls_and_scrape_ids_length_mismatch():
    analysis = AnalysisResult(output_cited="", output_clean="", citations=[])

    with patch("autoso.storage.supabase._get_client"):
        try:
            store_multi_result(
                urls=["https://a.com"],
                scrape_ids=[],
                mode="texture",
                analysis_mode="prompt",
                title="T",
                analysis=analysis,
            )
        except ValueError as exc:
            assert "same length" in str(exc)
        else:
            raise AssertionError("ValueError not raised")


def test_store_multi_result_inserts_analysis_source_rows_with_url_scrape_and_index():
    analysis = AnalysisResult(output_cited="", output_clean="", citations=[])
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

    source_inserts = [rows for name, rows in insert_log if name == "analysis_sources"]
    assert source_inserts
    rows = source_inserts[0]
    assert rows == [
        {
            "analysis_id": rows[0]["analysis_id"],
            "url": "https://a.com",
            "link_index": 0,
            "scrape_id": "sid-a",
        },
        {
            "analysis_id": rows[0]["analysis_id"],
            "url": "https://b.com",
            "link_index": 1,
            "scrape_id": "sid-b",
        },
    ]

