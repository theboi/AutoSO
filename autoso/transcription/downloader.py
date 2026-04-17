# autoso/transcription/downloader.py
import subprocess
import tempfile
from pathlib import Path


def download_audio(url: str, output_dir: str | None = None) -> str:
    """Download audio from a URL using yt-dlp. Returns path to MP3 file."""
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
