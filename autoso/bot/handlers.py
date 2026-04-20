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

import autoso.config as config
from autoso.bot.auth import require_auth
from autoso.pipeline.pipeline import run_pipeline
from autoso.transcription.transcription import transcribe_url

logger = logging.getLogger(__name__)

TELEGRAM_MAX_LENGTH = 4096
MAX_URLS = 50


class ArgParseError(ValueError):
    pass


def _split_message(text: str, limit: int = TELEGRAM_MAX_LENGTH) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


# Serial queue: prevents concurrent Playwright launches from OOM-crashing the browser.
_pipeline_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pipeline")


def _is_valid_url(text: str) -> bool:
    try:
        parsed = urlparse(text)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def _parse_analysis_args(args: list[str]) -> tuple[list[str], str, str | None]:
    if not args:
        raise ArgParseError("No arguments provided.")

    urls: list[str] = []
    analysis_mode = "prompt"
    title: str | None = None

    i = 0
    while i < len(args):
        token = args[i]

        if token in ("-m", "--mode"):
            if i + 1 >= len(args):
                raise ArgParseError("Missing value for -m/--mode.")
            mode_value = args[i + 1].strip().lower()
            if mode_value not in ("prompt", "rag"):
                raise ArgParseError(f"Invalid mode: {mode_value!r}. Use prompt or rag.")
            analysis_mode = mode_value
            i += 2
            continue

        if token.startswith('"') or token.startswith("'"):
            if title is not None:
                raise ArgParseError("Only one title is allowed.")
            quote = token[0]
            if len(token) > 1 and token.endswith(quote):
                title = token[1:-1]
                i += 1
                continue
            parts = [token[1:]]
            i += 1
            while i < len(args):
                part = args[i]
                if part.endswith(quote):
                    parts.append(part[:-1])
                    title = " ".join(parts)
                    i += 1
                    break
                parts.append(part)
                i += 1
            else:
                raise ArgParseError("Unterminated quoted title.")
            continue

        if token.startswith("-"):
            raise ArgParseError(f"Unknown option: {token!r}.")

        if _is_valid_url(token):
            urls.append(token)
            if len(urls) > MAX_URLS:
                raise ArgParseError(f"Too many URLs (max {MAX_URLS}).")
            i += 1
            continue

        raise ArgParseError(f"Invalid or stray token: {token!r}.")

    if not urls:
        raise ArgParseError("At least one valid URL is required.")

    return urls, analysis_mode, title


@require_auth
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "AutoSO ready.\n\n"
        '/texture <url> [url ...] [-m prompt|rag] ["Title"] — Texture analysis\n'
        '/bucket <url> [url ...] [-m prompt|rag] ["Title"] — Bucket analysis\n'
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
    usage = f'/{mode} <url> [url ...] [-m prompt|rag] ["Title"]'
    try:
        urls, analysis_mode, provided_title = _parse_analysis_args(context.args or [])
    except ArgParseError as e:
        await update.message.reply_text(f"{e}\nUsage: {usage}")
        return

    await update.message.reply_text(
        f"Queued {len(urls)} link(s) with {analysis_mode} mode. Processing now — this may take a minute."
    )

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            _pipeline_executor,
            functools.partial(
                run_pipeline,
                urls=urls,
                mode=mode,
                analysis_mode=analysis_mode,
                provided_title=provided_title,
            ),
        )
        output = result.output

        if len(output) > TELEGRAM_MAX_LENGTH:
            await update.message.reply_text(
                "Output too long for one message "
                f"({len(output)} chars). "
                f"View full citations: {config.CITATION_UI_BASE_URL.rstrip('/')}/{result.run_id}"
            )

        chunks = _split_message(output)
        for chunk in chunks:
            try:
                await update.message.reply_text(chunk, parse_mode="Markdown")
            except BadRequest:
                logger.warning("Markdown parse failed for run_id=%s — sending plain text", result.run_id)
                await update.message.reply_text(chunk)

    except Exception:
        logger.exception(
            "Pipeline error for urls=%s mode=%s analysis_mode=%s",
            urls,
            mode,
            analysis_mode,
        )
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
