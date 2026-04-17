# autoso/bot/handlers.py
import asyncio
import functools
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from autoso.bot.auth import require_auth
from autoso.pipeline.pipeline import run_pipeline
from autoso.transcription.transcription import transcribe_url

logger = logging.getLogger(__name__)

TELEGRAM_MAX_LENGTH = 4096

# Shared executor — pipeline runs (scrape + LLM) are CPU/IO-heavy synchronous work.
_pipeline_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="pipeline")


def _is_valid_url(text: str) -> bool:
    try:
        parsed = urlparse(text)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


@require_auth
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "AutoSO ready.\n\n"
        "/texture <url> [title] — Texture analysis\n"
        "/bucket <url> [title] — Bucket analysis\n"
        "/transcribe <url> [title] — Transcribe audio/video"
    )


@require_auth
async def texture_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _handle_analysis(update, context, mode="texture")


@require_auth
async def bucket_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _handle_analysis(update, context, mode="bucket")


async def _handle_analysis(
    update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str
):
    args = context.args
    if not args:
        await update.message.reply_text(f"Usage: /{mode} <url> [optional title]")
        return

    url = args[0]
    if not _is_valid_url(url):
        await update.message.reply_text(
            f"Invalid URL: {url!r}\nUsage: /{mode} <url> [optional title]"
        )
        return

    provided_title = " ".join(args[1:]) if len(args) > 1 else None

    await update.message.reply_text("Processing... this may take a minute.")

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            _pipeline_executor,
            functools.partial(run_pipeline, url=url, mode=mode, provided_title=provided_title),
        )
        output = result.output

        if len(output) > TELEGRAM_MAX_LENGTH:
            from autoso.config import CITATION_UI_BASE_URL

            logger.error(
                "Output exceeds Telegram limit: %d chars, run_id=%s",
                len(output),
                result.run_id,
            )
            truncated = output[: TELEGRAM_MAX_LENGTH - 200] + "\n\n[...truncated]"
            ui_msg = ""
            if CITATION_UI_BASE_URL:
                ui_msg = f"\nFull output with citations: {CITATION_UI_BASE_URL}/{result.run_id}"

            await update.message.reply_text(
                f"Output is {len(output)} chars (Telegram limit is {TELEGRAM_MAX_LENGTH}).{ui_msg}"
            )
            try:
                await update.message.reply_text(truncated, parse_mode="Markdown")
            except BadRequest:
                await update.message.reply_text(truncated)
            return

        try:
            await update.message.reply_text(output, parse_mode="Markdown")
        except BadRequest:
            logger.warning("Markdown parse failed for run_id=%s — sending plain text", result.run_id)
            await update.message.reply_text(output)

    except Exception:
        logger.exception("Pipeline error for url=%s mode=%s", url, mode)
        await update.message.reply_text(
            "An error occurred while processing your request. Check logs for details."
        )


@require_auth
async def transcribe_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /transcribe <url> [optional title]")
        return

    url = args[0]
    if not _is_valid_url(url):
        await update.message.reply_text(
            f"Invalid URL: {url!r}\nUsage: /transcribe <url> [optional title]"
        )
        return

    provided_title = " ".join(args[1:]) if len(args) > 1 else None

    await update.message.reply_text("Transcribing... this may take a few minutes.")

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            _pipeline_executor,
            functools.partial(transcribe_url, url=url, title=provided_title),
        )
        docx_path = result.docx_path
        filename = os.path.basename(docx_path)
        with open(docx_path, "rb") as f:
            await update.message.reply_document(document=f, filename=filename)
        try:
            os.unlink(docx_path)
        except OSError:
            pass
    except Exception:
        logger.exception("Transcription error for url=%s", url)
        await update.message.reply_text(
            "An error occurred during transcription. Check logs for details."
        )
