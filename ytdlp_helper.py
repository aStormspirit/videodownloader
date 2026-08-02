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
        "format": (
            "best[ext=mp4][protocol^=http][protocol!*=m3u8]/"
            "best[ext=mp4]/"
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
            "best"
        ),
        "merge_output_format": "mp4",
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
        with YoutubeDL(opts) as ydl:
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
    except YtDlpDownloadError as exc:
        raise DownloadError(f"{error_label}: {exc}") from exc
    except DownloadError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise DownloadError(f"{error_label}: {exc}") from exc
