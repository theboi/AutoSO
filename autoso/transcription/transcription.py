# autoso/transcription/transcription.py
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Optional

from supabase import create_client

import autoso.config as config
from autoso.transcription.docx_output import create_docx
from autoso.transcription.downloader import download_audio
from autoso.transcription.transcriber import transcribe

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    title: str
    transcript: str
    docx_path: str     # Caller must delete this file after sending
    run_id: str


def transcribe_url(url: str, title: Optional[str] = None) -> TranscriptionResult:
    """Download, transcribe, and store a video/audio URL."""
    audio_path = download_audio(url)
    logger.info("Downloaded audio: %s", audio_path)

    try:
        transcript, detected_language = transcribe(audio_path)
        logger.info("Transcribed %d chars, language=%s", len(transcript), detected_language)

        resolved_title = title or _title_from_url(url)

        docx_path = create_docx(resolved_title, transcript)

        run_id = _store_transcript(
            url=url,
            title=resolved_title,
            transcript=transcript,
            language=detected_language,
        )

        return TranscriptionResult(
            title=resolved_title,
            transcript=transcript,
            docx_path=docx_path,
            run_id=run_id,
        )
    finally:
        if os.path.exists(audio_path):
            try:
                os.unlink(audio_path)
            except OSError:
                pass


def _store_transcript(
    url: str, title: str, transcript: str, language: Optional[str]
) -> str:
    """Write a transcript row to Supabase. Returns the new run_id."""
    client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    run_id = str(uuid.uuid4())
    client.table("transcripts").insert(
        {
            "id": run_id,
            "url": url,
            "title": title,
            "transcript": transcript,
            "language": language,
        }
    ).execute()
    return run_id


def _title_from_url(url: str) -> str:
    """Extract a best-effort title from the URL when none is provided."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    if parts:
        return parts[-1].replace("-", " ").replace("_", " ").title()
    return parsed.netloc or url
