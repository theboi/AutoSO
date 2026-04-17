# tests/test_transcription/test_transcriber.py
import pytest
import tempfile
import os
from unittest.mock import patch, MagicMock
from autoso.transcription.transcriber import transcribe, _split_audio_if_needed


def _make_model_mock(text: str, language: str = "en") -> MagicMock:
    model = MagicMock()
    model.transcribe.return_value = {"text": text, "language": language}
    return model


def test_transcribe_returns_text_and_language(tmp_path):
    fake_audio = tmp_path / "audio.mp3"
    fake_audio.write_bytes(b"fake audio")

    with patch("autoso.transcription.transcriber._get_model") as mock_load, \
         patch("autoso.transcription.transcriber._split_audio_if_needed", return_value=[str(fake_audio)]):
        mock_load.return_value = _make_model_mock("NS training builds discipline.", "en")
        text, lang = transcribe(str(fake_audio))

    assert text == "NS training builds discipline."
    assert lang == "en"


def test_transcribe_detects_chinese(tmp_path):
    fake_audio = tmp_path / "audio.mp3"
    fake_audio.write_bytes(b"fake audio")

    with patch("autoso.transcription.transcriber._get_model") as mock_load, \
         patch("autoso.transcription.transcriber._split_audio_if_needed", return_value=[str(fake_audio)]):
        mock_load.return_value = _make_model_mock("军事训练很重要", "zh")
        text, lang = transcribe(str(fake_audio))

    assert lang == "zh"


def test_transcribe_joins_chunks():
    """Multiple audio chunks should be joined with a space."""
    chunks = ["/tmp/chunk1.mp3", "/tmp/chunk2.mp3"]

    def side_effect(path, **kwargs):
        idx = chunks.index(path)
        return {"text": f"Chunk {idx + 1} text.", "language": "en"}

    with patch("autoso.transcription.transcriber._get_model") as mock_load, \
         patch("autoso.transcription.transcriber._split_audio_if_needed", return_value=chunks):
        mock_model = MagicMock()
        mock_model.transcribe.side_effect = side_effect
        mock_load.return_value = mock_model
        text, lang = transcribe("/tmp/audio.mp3")

    assert "Chunk 1 text." in text
    assert "Chunk 2 text." in text
    assert lang == "en"


def test_transcribe_passes_language_when_provided(tmp_path):
    fake_audio = tmp_path / "audio.mp3"
    fake_audio.write_bytes(b"x")

    with patch("autoso.transcription.transcriber._get_model") as mock_load, \
         patch("autoso.transcription.transcriber._split_audio_if_needed", return_value=[str(fake_audio)]):
        model_mock = _make_model_mock("text")
        mock_load.return_value = model_mock
        transcribe(str(fake_audio), language="zh")

    call_kwargs = model_mock.transcribe.call_args.kwargs
    assert call_kwargs.get("language") == "zh"


def test_split_audio_if_needed_returns_single_file_when_small(tmp_path):
    small_file = tmp_path / "small.mp3"
    small_file.write_bytes(b"x" * 100)
    result = _split_audio_if_needed(str(small_file))
    assert result == [str(small_file)]
