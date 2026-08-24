#!/usr/bin/env python3
"""Shared yt-dlp download helper."""

from __future__ import annotations

import os
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError as YtDlpDownloadError

from common import DownloadError, safe_name


def _cookies_file() -> str | None:
    raw = os.getenv("YTDLP_COOKIES_FILE", "").strip()
    path = Path(raw) if raw else Path("cookies.txt")
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    # Real Netscape rows only (ignore comments / placeholders)
    has_rows = any(
        line
        and not line.startswith("#")
        and "\t" in line
        and "youtube" in line.lower()
        for line in text.splitlines()
    )
    if not has_rows:
        return None
    return str(path.resolve())


def download_with_ytdlp(
    url: str,
    output_dir: Path,
    *,
    prefix: str,
    error_label: str,
) -> list[Path]:
    """Download a single video with yt-dlp. Returns saved file paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(output_dir / f"{prefix}_%(uploader|unknown)s_%(id)s.%(ext)s")

    opts: dict = {
        "outtmpl": {"default": outtmpl},
        # Robust format selection:
        # 1) Prefer MP4/H.264 + M4A (Telegram-friendly) when available
        # 2) Fall back to progressive MP4
        # 3) Fall back to any best video+audio, then any single best stream
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
        # Prefer MP4/H.264/AAC when there is a tie, but do NOT require them
        "format_sort": ["ext:mp4:m4a:webm", "vcodec:h264", "acodec:aac", "res", "fps"],
        # Let yt-dlp choose the correct container; conversion isn't strictly required
        # "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 3,
        "fragment_retries": 3,
        "restrictfilenames": True,
        "noplaylist": True,
        # yt-dlp 2026+: YouTube n-challenge needs a JS runtime + yt-dlp-ejs
        "js_runtimes": {"node": {}},
        "remote_components": ["ejs:github"],
        "extractor_args": {
            # android clients skip cookies; prefer cookie-capable clients first
            "youtube": {"player_client": ["web", "tv", "mweb", "web_safari"]},
        },
    }

    cookies = _cookies_file()
    if cookies:
        opts["cookiefile"] = cookies
    else:
        # Without cookies, android clients still help on some networks
        opts["extractor_args"] = {
            "youtube": {"player_client": ["android", "android_vr", "web", "tv"]},
        }

    try:
        def _run_with_opts(run_opts: dict) -> list[Path]:
            with YoutubeDL(run_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info is None:
                    raise DownloadError(f"{error_label}: yt-dlp returned no video info.")

                if "entries" in info:
                    entries = [e for e in (info.get("entries") or []) if e]
                    if not entries:
                        raise DownloadError(f"{error_label}: no video found in the link.")
                    info = entries[0]

                filename = ydl.prepare_filename(info)
                path = Path(filename)
                if path.suffix.lower() != ".mp4":
                    mp4 = path.with_suffix(".mp4")
                    if mp4.exists():
                        path = mp4

                if not path.exists():
                    video_id = safe_name(str(info.get("id") or ""))
                    candidates = sorted(
                        output_dir.glob(f"{prefix}_*_{video_id}.*"),
                        key=lambda p: p.stat().st_mtime,
                        reverse=True,
                    )
                    if not candidates:
                        raise DownloadError(
                            f"{error_label}: download finished but file was not found."
                        )
                    path = candidates[0]

                return [path]

        # First attempt with MP4-preferred, robust fallbacks
        try:
            return _run_with_opts(opts)
        except YtDlpDownloadError as exc:
            msg = str(exc)
            # If the chosen format is unavailable, retry with the most permissive selector
            if "Requested format is not available" in msg or "no such format" in msg.lower():
                fallback_opts = dict(opts)
                fallback_opts["format"] = "bv*+ba/b"
                # Remove any format_sort bias to maximize availability
                fallback_opts.pop("format_sort", None)
                return _run_with_opts(fallback_opts)
            raise
    except YtDlpDownloadError as exc:
        raise DownloadError(f"{error_label}: {exc}") from exc
    except DownloadError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise DownloadError(f"{error_label}: {exc}") from exc
