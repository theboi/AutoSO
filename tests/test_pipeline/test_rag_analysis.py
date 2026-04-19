from unittest.mock import MagicMock, patch

from autoso.pipeline.analysis import AnalysisResult
from autoso.pipeline.flatten import FlatComment
from autoso.pipeline.pool import Pool, PoolItem
from autoso.pipeline.rag_analysis import _pool_documents, run_rag_analysis
from autoso.scraping.models import Post


def _post(url: str) -> Post:
    return Post(
        id=url,
        platform="facebook",
        url=url,
        page_title="",
        post_title="",
        date=None,
        author=None,
        content="",
        likes=None,
        comments=[],
    )


def _pool_two_sources() -> Pool:
    return Pool(
        items=[
            PoolItem(1, FlatComment("a1", 0, "alpha", [], 0)),
            PoolItem(2, FlatComment("b1", 0, "bravo", [], 1)),
            PoolItem(3, FlatComment("b2", 1, "charlie", [], 1)),
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


def test_pool_documents_have_rendered_text_and_metadata():
    pool = Pool(
        items=[
            PoolItem(1, FlatComment("a1", 0, "alpha", [], 0)),
            PoolItem(2, FlatComment("r1", 1, "reply", ["parent text"], 1)),
        ],
        posts=[_post("https://a.com"), _post("https://b.com")],
    )

    docs = _pool_documents(pool)

    assert len(docs) == 2
    assert docs[0].text == "[1] alpha"
    assert docs[0].metadata == {
        "comment_id": "a1",
        "position": 0,
        "source_index": 0,
        "citation_number": 1,
    }
    assert "↳ reply in thread" in docs[1].text
    assert "parent text" in docs[1].text
    assert docs[1].text.endswith("reply")
    assert docs[1].metadata["source_index"] == 1
    assert docs[1].metadata["citation_number"] == 2


def test_run_rag_analysis_returns_result_with_citations():
    pool = _pool_two_sources()

    fake_response = MagicMock()
    fake_response.__str__ = lambda self: "- bullet [1]\n- bullet [2]"
    fake_response.source_nodes = [
        _source_node("a1", 1, 0, 0, "[1] alpha"),
        _source_node("b1", 2, 1, 999, "[2] mutated text"),
    ]

    fake_engine = MagicMock()
    fake_engine.query.return_value = fake_response

    with patch("autoso.pipeline.rag_analysis.build_citation_engine", return_value=fake_engine), patch(
        "autoso.pipeline.rag_analysis.VectorStoreIndex.from_documents", return_value=MagicMock()
    ), patch("autoso.pipeline.rag_analysis.chromadb.EphemeralClient"):
        result = run_rag_analysis(
            mode="texture",
            title="T",
            pool=pool,
            hg_block=None,
        )

    assert isinstance(result, AnalysisResult)
    assert result.output_cited == "- bullet [1]\n- bullet [2]"
    assert result.output_clean == "- bullet\n- bullet"
    citation_numbers = sorted(r.citation_number for r in result.citations)
    assert citation_numbers == [1, 2]

    mapped = {r.citation_number: r for r in result.citations}
    assert mapped[2].text == "bravo"
    assert mapped[2].position == 0


def test_run_rag_analysis_dedupes_by_comment_id_and_source():
    pool = _pool_two_sources()
    fake_response = MagicMock()
    fake_response.__str__ = lambda self: "- bullet [1]"
    fake_response.source_nodes = [
        _source_node("a1", 1, 0, 0, "[1] alpha part 1"),
        _source_node("a1", 1, 0, 0, "[1] alpha part 2"),
    ]
    fake_engine = MagicMock()
    fake_engine.query.return_value = fake_response

    with patch("autoso.pipeline.rag_analysis.build_citation_engine", return_value=fake_engine), patch(
        "autoso.pipeline.rag_analysis.VectorStoreIndex.from_documents", return_value=MagicMock()
    ), patch("autoso.pipeline.rag_analysis.chromadb.EphemeralClient"):
        result = run_rag_analysis(
            mode="texture",
            title="T",
            pool=pool,
            hg_block=None,
        )

    assert len(result.citations) == 1


def test_run_rag_analysis_passes_similarity_top_k_equal_to_pool_size():
    pool = _pool_two_sources()
    fake_response = MagicMock()
    fake_response.__str__ = lambda self: "x"
    fake_response.source_nodes = []
    fake_engine = MagicMock()
    fake_engine.query.return_value = fake_response

    with patch("autoso.pipeline.rag_analysis.build_citation_engine", return_value=fake_engine) as mock_build, patch(
        "autoso.pipeline.rag_analysis.VectorStoreIndex.from_documents", return_value=MagicMock()
    ), patch("autoso.pipeline.rag_analysis.chromadb.EphemeralClient"):
        run_rag_analysis(mode="texture", title="T", pool=pool, hg_block=None)

    _, kwargs = mock_build.call_args
    assert kwargs["similarity_top_k"] == 3
    assert kwargs["citation_chunk_size"] == 4096
