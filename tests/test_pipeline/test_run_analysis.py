from unittest.mock import MagicMock, patch

from autoso.pipeline.analysis import AnalysisResult
from autoso.pipeline.flatten import FlatComment
from autoso.pipeline.pool import Pool, PoolItem
from autoso.pipeline.run_analysis import _render_node_text, run_analysis
from autoso.scraping.models import Post


def _post(url: str) -> Post:
    return Post(
        id=url,
        platform="reddit",
        url=url,
        page_title="",
        post_title="",
        date=None,
        author=None,
        content="post body",
        likes=None,
        comments=[],
    )


def _pool() -> Pool:
    return Pool(
        items=[
            PoolItem(1, FlatComment("a1", 0, "alpha", [], 0)),
            PoolItem(2, FlatComment("b1", 0, "bravo", ["parent text"], 1)),
            PoolItem(3, FlatComment("c1", 1, "charlie", [], 1)),
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


def test_render_node_text_top_level():
    item = PoolItem(5, FlatComment("c1", 0, "alpha text", [], 0))
    assert _render_node_text(item) == "alpha text"


def test_render_node_text_reply_includes_thread_no_bracket_prefix():
    item = PoolItem(12, FlatComment("r1", 4, "disagreed", ["parent says", "first reply"], 1))
    rendered = _render_node_text(item)
    assert not rendered.startswith("[12]")
    assert "↳ reply in thread" in rendered
    assert "parent: parent says" in rendered
    assert "· first reply" in rendered
    assert rendered.endswith("disagreed")


def test_run_analysis_uses_summary_index_not_vector_store():
    pool = _pool()
    fake_response = MagicMock()
    fake_response.__str__ = lambda self: "- bullet [1]\n- bullet [2]"
    fake_response.source_nodes = []
    fake_engine = MagicMock()
    fake_engine.query.return_value = fake_response

    with patch("autoso.pipeline.run_analysis.SummaryIndex") as MockIndex, patch(
        "autoso.pipeline.run_analysis.build_citation_engine", return_value=fake_engine
    ):
        run_analysis(mode="texture", title="T", pool=pool, hg_block=None)

    MockIndex.assert_called_once()
    args = MockIndex.call_args[0][0]
    assert len(args) == 3


def test_run_analysis_creates_text_nodes_with_metadata():
    pool = _pool()
    fake_response = MagicMock()
    fake_response.__str__ = lambda self: ""
    fake_response.source_nodes = []
    fake_engine = MagicMock()
    fake_engine.query.return_value = fake_response

    captured_nodes = []

    def capture_index(nodes):
        captured_nodes.extend(nodes)
        return MagicMock()

    with patch("autoso.pipeline.run_analysis.SummaryIndex", side_effect=capture_index), patch(
        "autoso.pipeline.run_analysis.build_citation_engine", return_value=fake_engine
    ):
        run_analysis(mode="texture", title="T", pool=pool, hg_block=None)

    assert len(captured_nodes) == 3
    assert captured_nodes[0].metadata["citation_number"] == 1
    assert captured_nodes[0].metadata["comment_id"] == "a1"
    assert captured_nodes[0].text == "alpha"
    assert captured_nodes[1].metadata["citation_number"] == 2
    assert "↳ reply in thread" in captured_nodes[1].text


def test_run_analysis_returns_result_with_citations():
    pool = _pool()
    fake_response = MagicMock()
    fake_response.__str__ = lambda self: "- bullet [1]\n- bullet [2]"
    fake_response.source_nodes = [
        _source_node("a1", 1, 0, 0, "alpha"),
        _source_node("b1", 2, 1, 0, "bravo"),
    ]
    fake_engine = MagicMock()
    fake_engine.query.return_value = fake_response

    with patch("autoso.pipeline.run_analysis.SummaryIndex"), patch(
        "autoso.pipeline.run_analysis.build_citation_engine", return_value=fake_engine
    ):
        result = run_analysis(mode="texture", title="T", pool=pool, hg_block=None)

    assert isinstance(result, AnalysisResult)
    assert result.output_cited == "- bullet [1]\n- bullet [2]"
    assert result.output_clean == "- bullet\n- bullet"
    citation_numbers = sorted(r.citation_number for r in result.citations)
    assert citation_numbers == [1, 2]
    mapped = {r.citation_number: r for r in result.citations}
    assert mapped[1].text == "alpha"
    assert mapped[1].comment_id == "a1"


def test_run_analysis_dedupes_by_comment_id_and_source():
    pool = _pool()
    fake_response = MagicMock()
    fake_response.__str__ = lambda self: "- bullet [1]"
    fake_response.source_nodes = [
        _source_node("a1", 1, 0, 0, "alpha part 1"),
        _source_node("a1", 1, 0, 0, "alpha part 2"),
    ]
    fake_engine = MagicMock()
    fake_engine.query.return_value = fake_response

    with patch("autoso.pipeline.run_analysis.SummaryIndex"), patch(
        "autoso.pipeline.run_analysis.build_citation_engine", return_value=fake_engine
    ):
        result = run_analysis(mode="texture", title="T", pool=pool, hg_block=None)

    assert len(result.citations) == 1


def test_run_analysis_passes_similarity_top_k_equal_to_pool_size():
    pool = _pool()
    fake_response = MagicMock()
    fake_response.__str__ = lambda self: ""
    fake_response.source_nodes = []
    fake_engine = MagicMock()
    fake_engine.query.return_value = fake_response

    with patch("autoso.pipeline.run_analysis.SummaryIndex"), patch(
        "autoso.pipeline.run_analysis.build_citation_engine", return_value=fake_engine
    ) as mock_build:
        run_analysis(mode="texture", title="T", pool=pool, hg_block=None)

    _, kwargs = mock_build.call_args
    assert kwargs["similarity_top_k"] == 3
    assert kwargs["citation_chunk_size"] == 2048


def test_run_analysis_bucket_passes_hg_block_in_query():
    pool = _pool()
    fake_response = MagicMock()
    fake_response.__str__ = lambda self: ""
    fake_response.source_nodes = []
    fake_engine = MagicMock()
    fake_engine.query.return_value = fake_response

    with patch("autoso.pipeline.run_analysis.SummaryIndex"), patch(
        "autoso.pipeline.run_analysis.build_citation_engine", return_value=fake_engine
    ):
        run_analysis(mode="bucket", title="T", pool=pool, hg_block="BUCKET_LABELS")

    query_arg = fake_engine.query.call_args[0][0]
    assert "BUCKET HOLY GRAIL REFERENCE:" in query_arg
    assert "BUCKET_LABELS" in query_arg


def test_run_analysis_raises_on_unknown_mode():
    pool = _pool()
    with patch("autoso.pipeline.run_analysis.SummaryIndex"), patch(
        "autoso.pipeline.run_analysis.build_citation_engine"
    ):
        try:
            run_analysis(mode="invalid", title="T", pool=pool, hg_block=None)
        except ValueError as e:
            assert "unknown mode" in str(e)
        else:
            raise AssertionError("expected ValueError")
