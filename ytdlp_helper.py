#!/usr/bin/env python3
"""Shared yt-dlp download helper."""

from __future__ import annotations

from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError as YtDlpDownloadError

from common import DownloadError, safe_name


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

    opts = {
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
