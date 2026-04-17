# autoso/transcription/transcriber.py
import os
import tempfile
from pathlib import Path
from typing import Optional

import whisper


_CHUNK_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB

_model_cache: dict = {}


def _get_model(model_name: str = "base"):
    if model_name not in _model_cache:
        _model_cache[model_name] = whisper.load_model(model_name)
    return _model_cache[model_name]


def transcribe(
    audio_path: str, language: Optional[str] = None
) -> tuple[str, Optional[str]]:
    """Transcribe an audio file using OpenAI Whisper v1 (base model).

    Returns (transcript_text, detected_language_code).
    """
    model = _get_model("base")
    chunks = _split_audio_if_needed(audio_path)

    parts = []
    detected_language: Optional[str] = None
    for chunk in chunks:
        kwargs: dict = {}
        if language:
            kwargs["language"] = language
        result = model.transcribe(chunk, **kwargs)
        parts.append(result["text"].strip())
        if detected_language is None:
            detected_language = result.get("language")

    return " ".join(parts), detected_language


def _split_audio_if_needed(audio_path: str) -> list[str]:
    """Return [audio_path] if small enough, otherwise split into 20-min chunks."""
    file_size = os.path.getsize(audio_path)
    if file_size <= _CHUNK_SIZE_BYTES:
        return [audio_path]

    try:
        from pydub import AudioSegment
    except ImportError:
        return [audio_path]

    audio = AudioSegment.from_mp3(audio_path)
    chunk_ms = 20 * 60 * 1000
    out_dir = tempfile.mkdtemp()
    chunks = []

    for i, start in enumerate(range(0, len(audio), chunk_ms)):
        chunk = audio[start : start + chunk_ms]
        chunk_path = str(Path(out_dir) / f"chunk_{i:04d}.mp3")
        chunk.export(chunk_path, format="mp3")
        chunks.append(chunk_path)

    return chunks
