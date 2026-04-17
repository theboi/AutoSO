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


def test_ingest_is_idempotent_no_append(tmp_path, monkeypatch):
    """Re-ingesting the same doc must replace the collection, not append to it."""
    import chromadb as _chromadb
    monkeypatch.setattr("autoso.config.CHROMADB_PATH", str(tmp_path))
    from autoso.pipeline.holy_grail import ingest_holy_grail

    doc_path = _write_temp_doc("Positive: Praised SAF capability\nNeutral: Discussed NS\n")
    try:
        ingest_holy_grail(doc_path)
        count_after_first = (
            _chromadb.PersistentClient(path=str(tmp_path))
            .get_collection("bucket_holy_grail")
            .count()
        )

        ingest_holy_grail(doc_path)
        count_after_second = (
            _chromadb.PersistentClient(path=str(tmp_path))
            .get_collection("bucket_holy_grail")
            .count()
        )

        assert count_after_first > 0
        assert count_after_second == count_after_first
    finally:
        os.unlink(doc_path)


def test_load_raises_runtime_error_if_not_ingested(tmp_path, monkeypatch):
    monkeypatch.setattr("autoso.config.CHROMADB_PATH", str(tmp_path))
    from autoso.pipeline.holy_grail import load_holy_grail
    with pytest.raises(RuntimeError, match="not found"):
        load_holy_grail()
