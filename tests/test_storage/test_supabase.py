# tests/test_storage/test_supabase.py
from unittest.mock import MagicMock, patch
from autoso.storage.supabase import store_result


def _mock_supabase_client():
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
    assert len(run_id) == 36
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

    table_names = [c.args[0] for c in client.table.call_args_list]
    assert "analyses" in table_names
    assert "citations" not in table_names
