from autoso.pipeline.flatten import FlatComment
from autoso.pipeline.pool import Pool, PoolItem, build_pool
from autoso.scraping.models import Post


def _flat(id_: str, pos: int, src: int, text: str = "x") -> FlatComment:
    return FlatComment(
        original_id=id_,
        position=pos,
        text=text,
        thread_context=[],
        source_index=src,
    )


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


def test_build_pool_single_source_numbers_from_one():
    flat_lists = [[_flat("a", 0, 0), _flat("b", 1, 0)]]
    posts = [_post("https://a.com")]

    pool = build_pool(posts, flat_lists)

    assert isinstance(pool, Pool)
    assert len(pool.items) == 2
    assert pool.items[0].citation_number == 1
    assert pool.items[1].citation_number == 2


def test_build_pool_multi_source_continues_numbering():
    flat_lists = [
        [_flat("a", 0, 0), _flat("b", 1, 0)],
        [_flat("c", 0, 1), _flat("d", 1, 1), _flat("e", 2, 1)],
    ]
    posts = [_post("https://a.com"), _post("https://b.com")]

    pool = build_pool(posts, flat_lists)

    assert [i.citation_number for i in pool.items] == [1, 2, 3, 4, 5]
    assert [i.flat.source_index for i in pool.items] == [0, 0, 1, 1, 1]


def test_lookup_by_citation_number():
    flat_lists = [[_flat("a", 0, 0)], [_flat("b", 0, 1)]]
    posts = [_post("https://a.com"), _post("https://b.com")]

    pool = build_pool(posts, flat_lists)

    assert pool.lookup(1).flat.original_id == "a"
    assert pool.lookup(2).flat.original_id == "b"


def test_lookup_unknown_citation_returns_none():
    pool = build_pool([_post("https://a.com")], [[_flat("a", 0, 0)]])
    assert pool.lookup(999) is None
