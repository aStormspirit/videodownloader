#!/usr/bin/env python3
"""Telegram bot: send a video link, get the file back."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import uuid
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

from common import OUTPUT_DIR, DownloadError
from instagram import download_instagram, extract_instagram_url
from threads import download_threads, extract_threads_url
from tiktok import download_tiktok, extract_tiktok_url
from vk import download_vk, extract_vk_url
from youtube import download_youtube, extract_youtube_url

# Telegram Bot API upload limit for bots (~50 MiB)
MAX_UPLOAD_BYTES = 49 * 1024 * 1024
DONATE_PAYLOAD = "donate-stars"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

_download_semaphore: asyncio.Semaphore | None = None
_busy_users: set[int] = set()
_busy_lock: asyncio.Lock | None = None


def _max_concurrent_downloads() -> int:
    raw = os.getenv("MAX_CONCURRENT_DOWNLOADS", "3").strip()
    try:
        value = int(raw)
    except ValueError:
        return 3
    return max(1, value)


def _donate_stars_amount() -> int:
    raw = os.getenv("DONATE_STARS", "50").strip()
    try:
        value = int(raw)
    except ValueError:
        return 50
    return max(1, value)


def _get_semaphore() -> asyncio.Semaphore:
    global _download_semaphore
    if _download_semaphore is None:
        _download_semaphore = asyncio.Semaphore(_max_concurrent_downloads())
    return _download_semaphore


def _get_busy_lock() -> asyncio.Lock:
    global _busy_lock
    if _busy_lock is None:
        _busy_lock = asyncio.Lock()
    return _busy_lock


def _allowed_user_ids() -> set[int] | None:
    raw = os.getenv("ALLOWED_USER_IDS", "").strip()
    if not raw:
        return None
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part:
            ids.add(int(part))
    return ids


def _is_allowed(user_id: int | None) -> bool:
    allowed = _allowed_user_ids()
    if allowed is None:
        return True
    return user_id is not None and user_id in allowed


def _resolve_download(text: str):
    threads_url = extract_threads_url(text)
    if threads_url:
        return threads_url, download_threads
    ig_url = extract_instagram_url(text)
    if ig_url:
        return ig_url, download_instagram
    yt_url = extract_youtube_url(text)
    if yt_url:
        return yt_url, download_youtube
    vk_url = extract_vk_url(text)
    if vk_url:
        return vk_url, download_vk
    tt_url = extract_tiktok_url(text)
    if tt_url:
        return tt_url, download_tiktok
    return None, None


def _job_output_dir(user_id: int) -> Path:
    return OUTPUT_DIR / f"{user_id}_{uuid.uuid4().hex}"


async def _send_donate_button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Send a message with a Telegram Stars donate button."""
    if not update.message:
        return
    amount = _donate_stars_amount()
    try:
        link = await context.bot.create_invoice_link(
            title="Поддержка бота",
            description=f"Спасибо за поддержку! Пожертвование {amount} ⭐",
            payload=DONATE_PAYLOAD,
            currency="XTR",
            prices=[LabeledPrice(label="Donate", amount=amount)],
        )
    except Exception:
        logger.exception("Failed to create Stars invoice link")
        return

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(f"Пожертвовать {amount} ⭐", url=link)]]
    )
    await update.message.reply_text(
        "Если бот полезен — можно поддержать звёздами ⭐",
        reply_markup=keyboard,
    )


async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.pre_checkout_query
    if not query:
        return
    if query.invoice_payload != DONATE_PAYLOAD:
        await query.answer(ok=False, error_message="Неверный платёж.")
        return
    await query.answer(ok=True)


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.successful_payment:
        return
    payment = update.message.successful_payment
    logger.info(
        "Stars donation: user=%s amount=%s %s charge=%s",
        update.effective_user.id if update.effective_user else None,
        payment.total_amount,
        payment.currency,
        payment.telegram_payment_charge_id,
    )
    await update.message.reply_text("Спасибо за поддержку! ⭐")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not _is_allowed(update.effective_user and update.effective_user.id):
        return
    await update.message.reply_text(
        "Пришли ссылку на Threads, Instagram, YouTube, VK или TikTok — "
        "скачаю видео и отправлю сюда."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not _is_allowed(update.effective_user and update.effective_user.id):
        return
    await update.message.reply_text(
        "Поддерживаются ссылки:\n"
        "• Threads — https://www.threads.com/…\n"
        "• Instagram — https://www.instagram.com/reel/… или /p/…\n"
        "• YouTube Shorts — https://www.youtube.com/shorts/…\n"
        "  (также youtube.com/watch и youtu.be)\n"
        "• VK — https://vk.com/video… или /clip…\n"
        "• TikTok — https://www.tiktok.com/@…/video/…\n"
        "  (также vm.tiktok.com / vt.tiktok.com)\n\n"
        "Бот скачает видео и пришлёт файл (лимит Telegram ~50 МБ)."
    )


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    user_id = user.id if user else None
    if not _is_allowed(user_id):
        await update.message.reply_text("Нет доступа.")
        return
    if user_id is None:
        return

    url, downloader = _resolve_download(update.message.text)
    if not url or not downloader:
        await update.message.reply_text(
            "Не вижу ссылку. Пришли URL Threads, Instagram, YouTube, VK или TikTok."
        )
        return

    lock = _get_busy_lock()
    async with lock:
        if user_id in _busy_users:
            await update.message.reply_text("Уже скачиваю твоё предыдущее видео, подожди.")
            return
        _busy_users.add(user_id)

    job_dir = _job_output_dir(user_id)
    status = None
    paths: list[Path] = []

    try:
        status = await update.message.reply_text("Скачиваю…")
        await update.message.chat.send_action(ChatAction.UPLOAD_VIDEO)

        async with _get_semaphore():
            try:
                paths = await asyncio.to_thread(downloader, url, job_dir)
            except DownloadError as exc:
                logger.warning("Download failed for %s: %s", url, exc)
                await status.edit_text(f"Не удалось скачать: {exc}")
                return
            except Exception:
                logger.exception("Unexpected download error for %s", url)
                await status.edit_text("Что-то пошло не так при скачивании.")
                return

            sent = 0
            for path in paths:
                size = path.stat().st_size
                if size > MAX_UPLOAD_BYTES:
                    await update.message.reply_text(
                        f"Файл {path.name} слишком большой для Telegram "
                        f"({size / (1024 * 1024):.1f} МБ, лимит ~50 МБ)."
                    )
                    continue

                await update.message.chat.send_action(ChatAction.UPLOAD_VIDEO)
                try:
                    with path.open("rb") as video:
                        await update.message.reply_video(
                            video=video,
                            filename=path.name,
                            supports_streaming=True,
                            write_timeout=120,
                            read_timeout=120,
                        )
                    sent += 1
                except Exception:
                    logger.exception("Failed to send video %s", path)
                    try:
                        with path.open("rb") as doc:
                            await update.message.reply_document(
                                document=doc,
                                filename=path.name,
                                write_timeout=120,
                                read_timeout=120,
                            )
                        sent += 1
                    except Exception:
                        logger.exception("Failed to send document %s", path)
                        await update.message.reply_text(
                            f"Не удалось отправить {path.name}."
                        )

            if sent:
                await status.edit_text(f"Готово ({sent}).")
                await _send_donate_button(update, context)
            else:
                await status.edit_text(
                    "Видео скачалось, но отправить в Telegram не удалось."
                )
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)
        async with lock:
            _busy_users.discard(user_id)


def main() -> None:
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "Set TELEGRAM_BOT_TOKEN in .env (get it from @BotFather)."
        )

    logger.info(
        "Config: max_concurrent=%s donate_stars=%s allowed_users=%s",
        _max_concurrent_downloads(),
        _donate_stars_amount(),
        "all" if _allowed_user_ids() is None else sorted(_allowed_user_ids() or []),
    )

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))

    logger.info("Bot starting…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
