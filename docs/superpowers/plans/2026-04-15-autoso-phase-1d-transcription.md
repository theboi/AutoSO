# AutoSO — Phase 1d: Transcription / Otters

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `/transcribe <url>` — downloads audio/video with yt-dlp, auto-detects language, transcribes with OpenAI Whisper, stores the transcript in Supabase, and returns a DOCX to the user via Telegram.

**Architecture:** Three focused modules (`downloader.py`, `transcriber.py`, `docx_output.py`) wired together in a `transcribe_url(url)` function. The Telegram handler calls `transcribe_url`, then sends the resulting DOCX as a file attachment. Long audio is chunked before Whisper to stay within Whisper's 25 MB / ~30-minute input limit.

**Tech Stack:** `yt-dlp` (CLI via subprocess), `openai-whisper` v1, `python-docx`, Supabase (existing), `python-telegram-bot` (existing), `pydub` (audio chunking)

**Pre-requisite:** Phase 1b complete. `migrations/001_initial_schema.sql` already applied. yt-dlp installed on PATH (`pip install yt-dlp`). FFmpeg installed on system (`brew install ffmpeg` / `apt install ffmpeg`).

---

## File Map

| File | Responsibility |
|------|---------------|
| `autoso/transcription/__init__.py` | Empty |
| `autoso/transcription/downloader.py` | `download_audio(url)` — yt-dlp wrapper, returns local MP3 path |
| `autoso/transcription/transcriber.py` | `transcribe(audio_path)` — Whisper, chunked for long audio, returns plain text |
| `autoso/transcription/docx_output.py` | `create_docx(title, transcript)` — returns path to `.docx` temp file |
| `autoso/transcription/transcription.py` | `transcribe_url(url, title)` — orchestrates the above + Supabase storage |
| `migrations/002_transcripts_table.sql` | `transcripts` table DDL |
| `tests/test_transcription/__init__.py` | Empty |
| `tests/test_transcription/test_downloader.py` | Downloader tests (mocked subprocess) |
| `tests/test_transcription/test_transcriber.py` | Transcriber tests (mocked Whisper) |
| `tests/test_transcription/test_docx_output.py` | DOCX generation tests |
| `tests/test_transcription/test_transcription.py` | Orchestrator tests |

Modify:
| `autoso/bot/handlers.py` | Add `/transcribe` handler |
| `autoso/bot/main.py` | Register `transcribe_handler` |

---

## Task 1: Database Schema for Transcripts

**Files:**
- Create: `migrations/002_transcripts_table.sql`

- [ ] **Step 1: Create `migrations/002_transcripts_table.sql`**

```sql
-- AutoSO transcripts table
-- Run in Supabase dashboard: SQL Editor after 001_initial_schema.sql

CREATE TABLE IF NOT EXISTS transcripts (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    url         TEXT        NOT NULL,
    title       TEXT        NOT NULL,
    transcript  TEXT        NOT NULL,    -- Full plain-text transcript
    language    TEXT,                    -- Detected language code (e.g. 'en', 'zh', 'ta')
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transcripts_created_at
    ON transcripts (created_at DESC);
```

- [ ] **Step 2: Apply schema in Supabase dashboard**

Open Supabase → SQL Editor → paste and run the above.

Expected: `transcripts` table created.

- [ ] **Step 3: Commit**

```bash
git add migrations/002_transcripts_table.sql
git commit -m "chore: add transcripts table schema"
```

---

## Task 2: Audio Downloader

**Files:**
- Create: `autoso/transcription/__init__.py`
- Create: `autoso/transcription/downloader.py`
- Create: `tests/test_transcription/__init__.py`
- Create: `tests/test_transcription/test_downloader.py`

- [ ] **Step 1: Create package files**

```bash
mkdir -p autoso/transcription tests/test_transcription
touch autoso/transcription/__init__.py tests/test_transcription/__init__.py
```

- [ ] **Step 2: Write failing tests**

```python
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
    # Simulate yt-dlp writing a file
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
    # yt-dlp returns 0 but writes nothing
    with patch("autoso.transcription.downloader.subprocess.run") as mock_run, \
         patch("autoso.transcription.downloader.tempfile.mkdtemp", return_value=str(tmp_path)):
        mock_run.return_value = _make_completed_process(0)
        with pytest.raises(RuntimeError, match="No audio file found"):
            download_audio("https://www.youtube.com/watch?v=abc123")


def test_download_audio_passes_correct_yt_dlp_args():
    import subprocess
    with patch("autoso.transcription.downloader.subprocess.run") as mock_run, \
         patch("autoso.transcription.downloader.tempfile.mkdtemp", return_value="/tmp/test"):
        import tempfile
        from pathlib import Path
        # Can't find file — just check args before the FileNotFoundError
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
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_transcription/test_downloader.py -v
```

Expected: `ImportError`.

- [ ] **Step 4: Create `autoso/transcription/downloader.py`**

```python
# autoso/transcription/downloader.py
import subprocess
import tempfile
from pathlib import Path


def download_audio(url: str, output_dir: str | None = None) -> str:
    """Download audio from a URL using yt-dlp.

    Returns the path to the downloaded MP3 file.
    Raises RuntimeError if yt-dlp fails or produces no output.
    """
    if output_dir is None:
        output_dir = tempfile.mkdtemp()

    output_template = str(Path(output_dir) / "%(id)s.%(ext)s")

    result = subprocess.run(
        [
            "yt-dlp",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "-o", output_template,
            url,
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr.strip()}")

    files = list(Path(output_dir).glob("*.mp3"))
    if not files:
        raise RuntimeError(
            f"No audio file found in {output_dir} after yt-dlp completed"
        )

    return str(files[0])
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_transcription/test_downloader.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add autoso/transcription/__init__.py autoso/transcription/downloader.py \
        tests/test_transcription/__init__.py tests/test_transcription/test_downloader.py
git commit -m "feat: add yt-dlp audio downloader"
```

---

## Task 3: Whisper Transcriber

**Files:**
- Create: `autoso/transcription/transcriber.py`
- Create: `tests/test_transcription/test_transcriber.py`

- [ ] **Step 1: Write failing tests**

```python
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

    with patch("autoso.transcription.transcriber.whisper.load_model") as mock_load, \
         patch("autoso.transcription.transcriber._split_audio_if_needed", return_value=[str(fake_audio)]):
        mock_load.return_value = _make_model_mock("NS training builds discipline.", "en")
        text, lang = transcribe(str(fake_audio))

    assert text == "NS training builds discipline."
    assert lang == "en"


def test_transcribe_detects_chinese(tmp_path):
    fake_audio = tmp_path / "audio.mp3"
    fake_audio.write_bytes(b"fake audio")

    with patch("autoso.transcription.transcriber.whisper.load_model") as mock_load, \
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

    with patch("autoso.transcription.transcriber.whisper.load_model") as mock_load, \
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

    with patch("autoso.transcription.transcriber.whisper.load_model") as mock_load, \
         patch("autoso.transcription.transcriber._split_audio_if_needed", return_value=[str(fake_audio)]):
        model_mock = _make_model_mock("text")
        mock_load.return_value = model_mock
        transcribe(str(fake_audio), language="zh")

    call_kwargs = model_mock.transcribe.call_args.kwargs
    assert call_kwargs.get("language") == "zh"


def test_split_audio_if_needed_returns_single_file_when_small(tmp_path):
    # File under 20 MB — should return as-is
    small_file = tmp_path / "small.mp3"
    small_file.write_bytes(b"x" * 100)
    result = _split_audio_if_needed(str(small_file))
    assert result == [str(small_file)]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_transcription/test_transcriber.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Create `autoso/transcription/transcriber.py`**

```python
# autoso/transcription/transcriber.py
import os
import tempfile
from pathlib import Path
from typing import Optional

import whisper


# Whisper base model's practical limit is ~25 MB / ~30 min
# Split anything over 20 MB to be safe
_CHUNK_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB


def transcribe(
    audio_path: str, language: Optional[str] = None
) -> tuple[str, Optional[str]]:
    """Transcribe an audio file using OpenAI Whisper v1 (base model).

    Splits the audio if it exceeds ~20 MB.
    Returns (transcript_text, detected_language_code).
    Language is from the first chunk (Whisper detects on the first 30 s).
    """
    model = whisper.load_model("base")
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
    """Return [audio_path] if small enough, otherwise split into chunks.

    Uses pydub for splitting — requires FFmpeg on PATH.
    """
    file_size = os.path.getsize(audio_path)
    if file_size <= _CHUNK_SIZE_BYTES:
        return [audio_path]

    try:
        from pydub import AudioSegment
    except ImportError:
        # pydub not installed — return as-is and let Whisper handle it
        return [audio_path]

    audio = AudioSegment.from_mp3(audio_path)
    # 20-minute chunks in milliseconds
    chunk_ms = 20 * 60 * 1000
    out_dir = tempfile.mkdtemp()
    chunks = []

    for i, start in enumerate(range(0, len(audio), chunk_ms)):
        chunk = audio[start : start + chunk_ms]
        chunk_path = str(Path(out_dir) / f"chunk_{i:04d}.mp3")
        chunk.export(chunk_path, format="mp3")
        chunks.append(chunk_path)

    return chunks
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_transcription/test_transcriber.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add autoso/transcription/transcriber.py tests/test_transcription/test_transcriber.py
git commit -m "feat: add Whisper transcriber with chunking support"
```

---

## Task 4: DOCX Output

**Files:**
- Create: `autoso/transcription/docx_output.py`
- Create: `tests/test_transcription/test_docx_output.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_transcription/test_docx_output.py
import os
import tempfile
from docx import Document
from autoso.transcription.docx_output import create_docx


def test_create_docx_returns_existing_file():
    path = create_docx("NS Exercise", "This is the full transcript text.")
    assert os.path.exists(path)
    assert path.endswith(".docx")
    os.unlink(path)


def test_create_docx_contains_title():
    path = create_docx("NS Exercise Transcript", "Some transcript content.")
    doc = Document(path)
    headings = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]
    assert any("NS Exercise Transcript" in h for h in headings)
    os.unlink(path)


def test_create_docx_contains_transcript_text():
    transcript = "SAF soldiers completed the exercise. NS training is important."
    path = create_docx("Title", transcript)
    doc = Document(path)
    full_text = " ".join(p.text for p in doc.paragraphs)
    assert "SAF soldiers completed the exercise" in full_text
    os.unlink(path)


def test_create_docx_writes_to_custom_path(tmp_path):
    out = str(tmp_path / "output.docx")
    result = create_docx("Title", "Text", output_path=out)
    assert result == out
    assert os.path.exists(out)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_transcription/test_docx_output.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Create `autoso/transcription/docx_output.py`**

```python
# autoso/transcription/docx_output.py
import tempfile
from typing import Optional

from docx import Document


def create_docx(
    title: str, transcript: str, output_path: Optional[str] = None
) -> str:
    """Create a DOCX file containing the transcript.

    Returns the path to the created file.
    If output_path is None, creates a temp file (caller is responsible for cleanup).
    """
    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
        output_path = tmp.name
        tmp.close()

    doc = Document()
    doc.add_heading(title, level=0)
    doc.add_paragraph(transcript)
    doc.save(output_path)
    return output_path
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_transcription/test_docx_output.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add autoso/transcription/docx_output.py tests/test_transcription/test_docx_output.py
git commit -m "feat: add DOCX transcript output generator"
```

---

## Task 5: Transcription Orchestrator + Supabase Storage

**Files:**
- Create: `autoso/transcription/transcription.py`
- Create: `tests/test_transcription/test_transcription.py`

- [ ] **Step 1: Write failing tests**

```python
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

        assert not os.path.exists(audio.name)  # audio cleaned up
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_transcription/test_transcription.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Create `autoso/transcription/transcription.py`**

```python
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
    """Download, transcribe, and store a video/audio URL.

    Returns a TranscriptionResult. The caller is responsible for deleting docx_path
    after sending it to the user.
    """
    # 1. Download
    audio_path = download_audio(url)
    logger.info("Downloaded audio: %s", audio_path)

    try:
        # 2. Transcribe — returns (text, detected_language_code)
        transcript, detected_language = transcribe(audio_path)
        logger.info("Transcribed %d chars, language=%s", len(transcript), detected_language)

        # 3. Title fallback
        resolved_title = title or _title_from_url(url)

        # 4. DOCX
        docx_path = create_docx(resolved_title, transcript)

        # 5. Store
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
        # Always clean up the downloaded audio
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
    # Use the path's last segment, or the domain as fallback
    parts = [p for p in parsed.path.split("/") if p]
    if parts:
        return parts[-1].replace("-", " ").replace("_", " ").title()
    return parsed.netloc or url
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_transcription/test_transcription.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add autoso/transcription/transcription.py tests/test_transcription/test_transcription.py
git commit -m "feat: add transcription orchestrator with Supabase storage"
```

---

## Task 6: `/transcribe` Telegram Handler

**Files:**
- Modify: `autoso/bot/handlers.py` — add `transcribe_handler`
- Modify: `autoso/bot/main.py` — register handler

- [ ] **Step 1: Write failing tests**

```python
# tests/test_bot/test_transcribe_handler.py
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from autoso.transcription.transcription import TranscriptionResult


def _make_update(user_id: int, args: list[str]):
    update = MagicMock()
    update.effective_user.id = user_id
    update.message.reply_text = AsyncMock()
    update.message.reply_document = AsyncMock()
    context = MagicMock()
    context.args = args
    return update, context


@pytest.fixture(autouse=True)
def whitelist_user():
    with patch("autoso.config.WHITELISTED_USER_IDS", {99}):
        yield


async def test_transcribe_handler_no_args_sends_usage():
    from autoso.bot.handlers import transcribe_handler
    update, context = _make_update(99, [])
    await transcribe_handler(update, context)
    text = update.message.reply_text.call_args.args[0]
    assert "Usage" in text


async def test_transcribe_handler_sends_docx():
    fake_docx = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
    fake_docx.close()

    try:
        from autoso.bot.handlers import transcribe_handler
        update, context = _make_update(99, ["https://www.youtube.com/watch?v=abc"])

        mock_result = TranscriptionResult(
            title="Test Video",
            transcript="Full transcript.",
            docx_path=fake_docx.name,
            run_id="run-123",
        )

        with patch("autoso.bot.handlers.transcribe_url", return_value=mock_result):
            await transcribe_handler(update, context)

        update.message.reply_document.assert_called_once()
        call_kwargs = update.message.reply_document.call_args
        # The document arg should be the open file
        assert not os.path.exists(fake_docx.name)  # cleaned up after send
    finally:
        if os.path.exists(fake_docx.name):
            os.unlink(fake_docx.name)


async def test_transcribe_handler_replies_on_error():
    from autoso.bot.handlers import transcribe_handler
    update, context = _make_update(99, ["https://www.youtube.com/watch?v=bad"])

    with patch("autoso.bot.handlers.transcribe_url", side_effect=RuntimeError("download failed")):
        await transcribe_handler(update, context)

    calls = [str(c) for c in update.message.reply_text.call_args_list]
    assert any("error" in c.lower() for c in calls)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_bot/test_transcribe_handler.py -v
```

Expected: `AttributeError` or `ImportError` — `transcribe_handler` not in `handlers.py` yet.

- [ ] **Step 3: Add `transcribe_handler` to `autoso/bot/handlers.py`**

Add the following at the bottom of the existing `autoso/bot/handlers.py`:

```python
@require_auth
async def transcribe_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /transcribe <url>")
        return

    url = args[0]
    provided_title = " ".join(args[1:]) if len(args) > 1 else None

    await update.message.reply_text("Transcribing... this may take a few minutes.")

    try:
        from autoso.transcription.transcription import transcribe_url
        import os

        result = transcribe_url(url=url, title=provided_title)

        with open(result.docx_path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=f"{result.title}.docx",
                caption=f"Transcript: {result.title}",
            )

        os.unlink(result.docx_path)

    except Exception:
        logger.exception("Transcription error for url=%s", url)
        await update.message.reply_text(
            "An error occurred during transcription. Check logs for details."
        )
```

- [ ] **Step 4: Register handler in `autoso/bot/main.py`**

Update the `main()` function to also import and register `transcribe_handler`:

```python
# autoso/bot/main.py
import logging
from telegram.ext import Application, CommandHandler
from autoso.config import TELEGRAM_TOKEN
from autoso.bot.handlers import (
    start_handler,
    texture_handler,
    bucket_handler,
    transcribe_handler,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("texture", texture_handler))
    app.add_handler(CommandHandler("bucket", bucket_handler))
    app.add_handler(CommandHandler("transcribe", transcribe_handler))
    app.run_polling()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_bot/test_transcribe_handler.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Run full suite**

```bash
pytest -v
```

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add autoso/bot/handlers.py autoso/bot/main.py \
        tests/test_bot/test_transcribe_handler.py
git commit -m "feat: add /transcribe handler — Phase 1d complete"
```

---

## Task 7: End-to-End Smoke Test (Manual)

- [ ] **Step 1: Start the bot**

```bash
python -m autoso.bot.main
```

- [ ] **Step 2: Send a transcription command**

From a whitelisted Telegram account, send:

```
/transcribe https://www.youtube.com/watch?v=REAL_VIDEO_ID
```

Expected: "Transcribing..." message, then a `.docx` file attachment.

- [ ] **Step 3: Open the DOCX**

Open the received `.docx` file. Verify:
- Heading = video title or extracted title
- Body = transcript text in the correct language

- [ ] **Step 4: Verify Supabase row**

Supabase → `transcripts` table: confirm row with correct `url`, `title`, `transcript`.

- [ ] **Step 5: Commit smoke test result**

```bash
git commit --allow-empty -m "test: Phase 1d transcription smoke test passed"
```
