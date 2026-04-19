# tests/test_pipeline/test_citation.py
import re
from unittest.mock import MagicMock

from autoso.pipeline.citation import extract_citations, strip_citation_markers


def _make_source_node(text: str, platform: str, node_id: str, position: int):
    node = MagicMock()
    node.node.text = text
    node.node.metadata = {
        "platform": platform,
        "id": node_id,
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
    assert citations[1].id == "ig_5"
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
