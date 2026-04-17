# tests/test_transcription/test_transcription.py
import os
import tempfile
from unittest.mock import patch, MagicMock
from autoso.transcription.transcription import transcribe_url, TranscriptionResult


def test_transcribe_url_returns_result():
    fake_docx = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
    fake_docx.close()

    try:
        with patch("autoso.transcription.transcription.download_audio", return_value="/tmp/audio.mp3"), \
             patch("autoso.transcription.transcription.transcribe", return_value=("Full transcript here.", "en")), \
             patch("autoso.transcription.transcription.create_docx", return_value=fake_docx.name), \
             patch("autoso.transcription.transcription._store_transcript", return_value="run-xyz"):

            result = transcribe_url(
                url="https://www.youtube.com/watch?v=abc",
                title="NS Exercise Video",
            )

        assert isinstance(result, TranscriptionResult)
        assert result.transcript == "Full transcript here."
        assert result.docx_path == fake_docx.name
        assert result.run_id == "run-xyz"
        assert result.title == "NS Exercise Video"
    finally:
        os.unlink(fake_docx.name)


def test_transcribe_url_cleans_up_audio_on_success():
    import tempfile as tf
    audio = tf.NamedTemporaryFile(suffix=".mp3", delete=False)
    audio.close()

    fake_docx = tf.NamedTemporaryFile(suffix=".docx", delete=False)
    fake_docx.close()

    try:
        with patch("autoso.transcription.transcription.download_audio", return_value=audio.name), \
             patch("autoso.transcription.transcription.transcribe", return_value=("text", "en")), \
             patch("autoso.transcription.transcription.create_docx", return_value=fake_docx.name), \
             patch("autoso.transcription.transcription._store_transcript", return_value="r1"):
            transcribe_url("https://youtube.com/watch?v=x", title="T")

        assert not os.path.exists(audio.name)
    finally:
        if os.path.exists(fake_docx.name):
            os.unlink(fake_docx.name)
        if os.path.exists(audio.name):
            os.unlink(audio.name)


def test_store_transcript_inserts_row():
    from unittest.mock import MagicMock, patch
    from autoso.transcription.transcription import _store_transcript

    mock_client = MagicMock()
    execute_result = MagicMock()
    mock_client.table.return_value.insert.return_value.execute.return_value = execute_result

    with patch("autoso.transcription.transcription.create_client", return_value=mock_client):
        run_id = _store_transcript(
            url="https://youtube.com/watch?v=abc",
            title="Test",
            transcript="Full text",
            language="en",
        )

    assert isinstance(run_id, str)
    assert len(run_id) == 36
    mock_client.table.assert_called_with("transcripts")
