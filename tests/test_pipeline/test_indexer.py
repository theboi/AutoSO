# tests/test_pipeline/test_indexer.py
import pytest
from unittest.mock import patch
from autoso.scraping.models import Comment
from autoso.pipeline.indexer import index_comments


def _make_comments(n: int) -> list[Comment]:
    return [
        Comment(
            platform="reddit",
            text=f"Comment {i}: NS training builds discipline and teamwork",
            comment_id=f"c{i}",
            position=i,
        )
        for i in range(n)
    ]


@pytest.mark.skip(reason="requires live LLM for query")
def test_index_returns_queryable_index():
    comments = _make_comments(5)
    index = index_comments(comments)
    engine = index.as_query_engine()
    response = engine.query("What do people think about NS?")
    assert str(response)


def test_index_stores_platform_metadata():
    comments = _make_comments(3)
    index = index_comments(comments)
    retriever = index.as_retriever(similarity_top_k=3)
    nodes = retriever.retrieve("NS training")
    for node in nodes:
        assert node.node.metadata["platform"] == "reddit"
        assert "comment_id" in node.node.metadata
        assert "position" in node.node.metadata


@pytest.mark.skip(reason="requires live LLM for query")
def test_two_runs_are_independent():
    c1 = _make_comments(2)
    c2 = [Comment(platform="instagram", text="IG comment about SAF", comment_id="ig0", position=0)]
    idx1 = index_comments(c1)
    idx2 = index_comments(c2)
    assert str(idx1.as_query_engine().query("NS"))
    assert str(idx2.as_query_engine().query("SAF"))


@pytest.mark.skip(reason="requires live LLM for query")
def test_empty_comments_returns_empty_index():
    index = index_comments([])
    engine = index.as_query_engine()
    response = engine.query("NS")
    assert response is not None
