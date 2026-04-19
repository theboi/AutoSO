import pytest

from autoso.pipeline.scaling import comments_per_link


def test_single_link_returns_500():
    assert comments_per_link(1) == 500


def test_ten_links_returns_500_each():
    assert comments_per_link(10) == 500


def test_eleven_links_scales_down():
    assert comments_per_link(11) == 454


def test_twenty_links_returns_250():
    assert comments_per_link(20) == 250


def test_fifty_links_returns_100():
    assert comments_per_link(50) == 100


def test_zero_links_raises():
    with pytest.raises(ValueError):
        comments_per_link(0)


def test_negative_links_raises():
    with pytest.raises(ValueError):
        comments_per_link(-3)
