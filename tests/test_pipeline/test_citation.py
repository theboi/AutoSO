import re
from unittest.mock import MagicMock, patch

from autoso.pipeline.citation import build_citation_engine, strip_citation_markers


def test_build_citation_engine_uses_default_chunk_size():
    index = MagicMock()
    with patch("autoso.pipeline.citation.CitationQueryEngine.from_args", return_value=MagicMock()) as mock_from_args:
        build_citation_engine(index)

    _, kwargs = mock_from_args.call_args
    assert kwargs["similarity_top_k"] == 10
    assert kwargs["citation_chunk_size"] == 512
    assert "text_qa_template" not in kwargs


def test_build_citation_engine_accepts_custom_chunk_size_and_prompt():
    index = MagicMock()
    with patch("autoso.pipeline.citation.CitationQueryEngine.from_args", return_value=MagicMock()) as mock_from_args:
        build_citation_engine(index, similarity_top_k=7, system_prompt="do x", citation_chunk_size=4096)

    _, kwargs = mock_from_args.call_args
    assert kwargs["similarity_top_k"] == 7
    assert kwargs["citation_chunk_size"] == 4096
    assert "text_qa_template" in kwargs


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
    assert not re.search(r"\[\d+\]", result)
    assert "Point about SAF" in result
