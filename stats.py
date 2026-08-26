#!/usr/bin/env python3
"""Persistent usage statistics (downloads, users, donations).

Stored as SQLite in the `downloads` volume so it survives container
recreation (redeploys). All writes are guarded by a lock because they may
be called from the asyncio event loop while downloads run in threads.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from common import OUTPUT_DIR

DB_PATH = OUTPUT_DIR / "stats.db"

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.execute(
            """
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                user_id INTEGER,
                username TEXT,
                platform TEXT,
                files INTEGER NOT NULL DEFAULT 0,
                bytes INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        _conn.execute(
            """
            CREATE TABLE IF NOT EXISTS donations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                user_id INTEGER,
                amount INTEGER,
                currency TEXT,
                charge_id TEXT
            )
            """
        )
        _conn.commit()
    return _conn


def record_download(
    user_id: int | None,
    username: str | None,
    platform: str,
    files: int,
    total_bytes: int,
) -> None:
    """Record one successful download event. Never raises."""
    try:
        with _lock:
            conn = _connect()
            conn.execute(
                "INSERT INTO downloads (ts, user_id, username, platform, files, bytes)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (_now(), user_id, username, platform, files, total_bytes),
            )
            conn.commit()
    except Exception:  # noqa: BLE001 - stats must never break the bot
        pass


def record_donation(
    user_id: int | None,
    amount: int | None,
    currency: str | None,
    charge_id: str | None,
) -> None:
    """Record one Stars donation. Never raises."""
    try:
        with _lock:
            conn = _connect()
            conn.execute(
                "INSERT INTO donations (ts, user_id, amount, currency, charge_id)"
                " VALUES (?, ?, ?, ?, ?)",
                (_now(), user_id, amount, currency, charge_id),
            )
            conn.commit()
    except Exception:  # noqa: BLE001
        pass


def summary() -> str:
    """Return a human-readable stats report (Telegram-friendly)."""
    try:
        with _lock:
            conn = _connect()
            cur = conn.cursor()

            total_dl, total_files, total_bytes, total_users = cur.execute(
                "SELECT COUNT(*), COALESCE(SUM(files), 0), COALESCE(SUM(bytes), 0),"
                " COUNT(DISTINCT user_id) FROM downloads"
            ).fetchone()

            by_platform = cur.execute(
                "SELECT platform, COUNT(*) AS n FROM downloads"
                " GROUP BY platform ORDER BY n DESC"
            ).fetchall()

            first_ts = cur.execute(
                "SELECT MIN(ts) FROM downloads"
            ).fetchone()[0]

            donations_count, donations_amount = cur.execute(
                "SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM donations"
            ).fetchone()

            top_users = cur.execute(
                "SELECT user_id, username, COUNT(*) AS n FROM downloads"
                " GROUP BY user_id ORDER BY n DESC LIMIT 5"
            ).fetchall()
    except Exception as exc:  # noqa: BLE001
        return f"Не удалось прочитать статистику: {exc}"

    gib = total_bytes / (1024 * 1024 * 1024)
    lines = [
        "📊 Статистика бота",
        f"С: {first_ts or '—'}",
        "",
        f"Скачиваний: {total_dl}",
        f"Отправлено файлов: {total_files}",
        f"Уникальных пользователей: {total_users}",
        f"Объём: {gib:.2f} ГБ",
        "",
        "По платформам:",
    ]
    if by_platform:
        lines += [f"  • {platform}: {n}" for platform, n in by_platform]
    else:
        lines.append("  —")

    lines += ["", f"Донаты: {donations_count} на {donations_amount} ⭐"]

    if top_users:
        lines += ["", "Топ пользователей:"]
        for user_id, username, n in top_users:
            handle = username or "-"
            lines.append(f"  • {handle} (id={user_id}): {n}")

    return "\n".join(lines)
