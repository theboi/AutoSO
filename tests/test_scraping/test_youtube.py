import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autoso.scraping.models import Post, ScrapeError
from autoso.scraping.youtube import YouTubeScraper


def _fake_info_json(tmp_path: Path, data: dict) -> Path:
    info = tmp_path / "abc123.info.json"
    info.write_text(json.dumps(data))
    return info


@patch("autoso.scraping.youtube.subprocess.run")
@patch("autoso.scraping.youtube.tempfile.mkdtemp")
def test_scrape_parses_info_json(mock_mkdtemp, mock_run, tmp_path):
    mock_mkdtemp.return_value = str(tmp_path)
    data = {
        "id": "abc123",
        "title": "Test Video",
        "description": "Video body",
        "channel": "MINDEF",
        "upload_date": "20260418",
        "like_count": 100,
        "comments": [
            {
                "id": "c1",
                "author": "u1",
                "text": "Top",
                "timestamp": 1713436800,
                "like_count": 5,
                "parent": "root",
            },
            {
                "id": "r1",
                "author": "u2",
                "text": "Reply",
                "timestamp": 1713436900,
                "like_count": 1,
                "parent": "c1",
            },
            {
                "id": "c2",
                "author": "u3",
                "text": "Second top",
                "timestamp": 1713437000,
                "like_count": 3,
                "parent": "root",
            },
        ],
    }
    _fake_info_json(tmp_path, data)
    mock_run.return_value = MagicMock(returncode=0, stderr="")

    scraper = YouTubeScraper()
    post = scraper.scrape("https://www.youtube.com/watch?v=abc123")

    assert isinstance(post, Post)
    assert post.platform == "youtube"
    assert post.id == "abc123"
    assert post.post_title == "Test Video"
    assert post.author == "MINDEF"
    assert post.likes == 100
    assert post.content == "Video body"
    assert post.date is not None
    assert len(post.comments) == 2
    assert post.comments[0].id == "c1"
    assert post.comments[0].likes == 5
    assert len(post.comments[0].subcomments) == 1
    assert post.comments[0].subcomments[0].id == "r1"
    assert post.comments[1].id == "c2"
    assert post.comments[1].subcomments == []


@patch("autoso.scraping.youtube.subprocess.run")
@patch("autoso.scraping.youtube.tempfile.mkdtemp")
def test_scrape_raises_on_yt_dlp_error(mock_mkdtemp, mock_run, tmp_path):
    mock_mkdtemp.return_value = str(tmp_path)
    mock_run.return_value = MagicMock(returncode=1, stderr="video unavailable")

    scraper = YouTubeScraper()
    with pytest.raises(ScrapeError):
        scraper.scrape("https://www.youtube.com/watch?v=x")
