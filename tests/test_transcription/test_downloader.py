# tests/test_transcription/test_downloader.py
import os
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from autoso.transcription.downloader import download_audio


def _make_completed_process(returncode: int, stderr: str = "") -> MagicMock:
    p = MagicMock(spec=subprocess.CompletedProcess)
    p.returncode = returncode
    p.stderr = stderr
    return p


def test_download_audio_returns_mp3_path(tmp_path):
    fake_file = tmp_path / "abc123.mp3"
    fake_file.write_bytes(b"fake audio data")

    with patch("autoso.transcription.downloader.subprocess.run") as mock_run, \
         patch("autoso.transcription.downloader.tempfile.mkdtemp", return_value=str(tmp_path)):
        mock_run.return_value = _make_completed_process(0)
        result = download_audio("https://www.youtube.com/watch?v=abc123")

    assert result.endswith(".mp3")
    assert os.path.dirname(result) == str(tmp_path)


def test_download_audio_raises_on_yt_dlp_failure(tmp_path):
    with patch("autoso.transcription.downloader.subprocess.run") as mock_run, \
         patch("autoso.transcription.downloader.tempfile.mkdtemp", return_value=str(tmp_path)):
        mock_run.return_value = _make_completed_process(1, "ERROR: video unavailable")
        with pytest.raises(RuntimeError, match="yt-dlp failed"):
            download_audio("https://www.youtube.com/watch?v=bad")


def test_download_audio_raises_when_no_file_created(tmp_path):
    with patch("autoso.transcription.downloader.subprocess.run") as mock_run, \
         patch("autoso.transcription.downloader.tempfile.mkdtemp", return_value=str(tmp_path)):
        mock_run.return_value = _make_completed_process(0)
        with pytest.raises(RuntimeError, match="No audio file found"):
            download_audio("https://www.youtube.com/watch?v=abc123")


def test_download_audio_passes_correct_yt_dlp_args():
    with patch("autoso.transcription.downloader.subprocess.run") as mock_run, \
         patch("autoso.transcription.downloader.tempfile.mkdtemp", return_value="/tmp/test"):
        mock_run.return_value = _make_completed_process(0)
        try:
            download_audio("https://youtu.be/XYZ")
        except RuntimeError:
            pass

    call_args = mock_run.call_args.args[0]
    assert "yt-dlp" in call_args
    assert "--extract-audio" in call_args
    assert "--audio-format" in call_args
    assert "mp3" in call_args
