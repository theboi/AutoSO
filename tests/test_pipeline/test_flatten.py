from autoso.pipeline.flatten import FlatComment, flatten_post_comments
from autoso.scraping.models import Comment, Post


def _comment(id_: str, text: str, position: int, replies=None) -> Comment:
    return Comment(
        id=id_,
        platform="facebook",
        author=None,
        date=None,
        text=text,
        likes=None,
        position=position,
        subcomments=list(replies or []),
    )


def _post(comments: list[Comment]) -> Post:
    return Post(
        id="p1",
        platform="facebook",
        url="https://facebook.com/x",
        page_title="pg",
        post_title="pt",
        date=None,
        author=None,
        content="c",
        likes=None,
        comments=comments,
    )


def test_single_top_level_no_replies():
    post = _post([_comment("a", "alpha", 0)])

    result = flatten_post_comments(post, n_cap=500, source_index=0)

    assert len(result) == 1
    assert result[0] == FlatComment(
        original_id="a",
        position=0,
        text="alpha",
        thread_context=[],
        source_index=0,
    )


def test_multiple_top_level_no_replies():
    post = _post([
        _comment("a", "alpha", 0),
        _comment("b", "bravo", 1),
        _comment("c", "charlie", 2),
    ])

    result = flatten_post_comments(post, n_cap=500, source_index=3)

    assert [r.text for r in result] == ["alpha", "bravo", "charlie"]
    assert all(r.thread_context == [] for r in result)
    assert all(r.source_index == 3 for r in result)


def test_parent_with_three_replies_builds_thread_context():
    post = _post([
        _comment("p", "parent", 0, replies=[
            _comment("r1", "reply1", 0),
            _comment("r2", "reply2", 1),
            _comment("r3", "reply3", 2),
        ]),
    ])

    result = flatten_post_comments(post, n_cap=500, source_index=0)

    assert [r.text for r in result] == ["parent", "reply1", "reply2", "reply3"]
    assert result[0].thread_context == []
    assert result[1].thread_context == ["parent"]
    assert result[2].thread_context == ["parent", "reply1"]
    assert result[3].thread_context == ["parent", "reply1", "reply2"]
    assert [r.position for r in result] == [0, 1, 2, 3]


def test_reply_text_has_no_prepend():
    post = _post([
        _comment("p", "parent", 0, replies=[_comment("r1", "the actual reply", 0)]),
    ])

    result = flatten_post_comments(post, n_cap=500, source_index=0)

    assert result[1].text == "the actual reply"
    assert "parent" not in result[1].text


def test_thread_caps_at_10_messages_parent_plus_9_replies():
    replies = [_comment(f"r{i}", f"reply{i}", i) for i in range(12)]
    post = _post([_comment("p", "parent", 0, replies=replies)])

    result = flatten_post_comments(post, n_cap=500, source_index=0)

    assert len(result) == 10
    assert [r.text for r in result] == (["parent"] + [f"reply{i}" for i in range(9)])
    assert len(result[-1].thread_context) == 9


def test_next_top_level_visited_after_capped_thread():
    replies = [_comment(f"r{i}", f"reply{i}", i) for i in range(15)]
    post = _post([
        _comment("p1", "parent1", 0, replies=replies),
        _comment("p2", "parent2", 1),
    ])

    result = flatten_post_comments(post, n_cap=500, source_index=0)

    texts = [r.text for r in result]
    assert texts[:10] == ["parent1"] + [f"reply{i}" for i in range(9)]
    assert texts[10] == "parent2"


def test_n_cap_truncates_mid_thread():
    replies = [_comment(f"r{i}", f"reply{i}", i) for i in range(5)]
    post = _post([
        _comment("p1", "parent1", 0, replies=replies),
        _comment("p2", "parent2", 1),
    ])

    result = flatten_post_comments(post, n_cap=3, source_index=0)

    assert [r.text for r in result] == ["parent1", "reply0", "reply1"]


def test_empty_post():
    post = _post([])

    result = flatten_post_comments(post, n_cap=500, source_index=0)

    assert result == []


def test_source_index_propagates():
    post = _post([
        _comment("p", "parent", 0, replies=[_comment("r1", "reply", 0)]),
    ])

    result = flatten_post_comments(post, n_cap=500, source_index=7)

    assert all(r.source_index == 7 for r in result)
