#!/usr/bin/env python3
"""Download video from a YouTube Shorts (or YouTube) URL via yt-dlp."""

from __future__ import annotations

import re
from pathlib import Path

from common import OUTPUT_DIR, DownloadError
from ytdlp_helper import download_with_ytdlp

YOUTUBE_URL_RE = re.compile(
    r"https?://(?:(?:www|m|music)\.)?"
    r"(?:"
    r"youtube\.com/(?:shorts/[\w\-]+|watch\?[^\s]*\bv=[\w\-]+|live/[\w\-]+|embed/[\w\-]+)"
    r"|youtu\.be/[\w\-]+"
    r")[^\s]*",
    re.IGNORECASE,
)


def extract_youtube_url(text: str) -> str | None:
    match = YOUTUBE_URL_RE.search(text)
    if not match:
        return None
    return match.group(0).rstrip(").,]}>\"'")


def download_youtube(url: str, output_dir: Path = OUTPUT_DIR) -> list[Path]:
    """Download a YouTube / Shorts video. Returns saved file paths."""
    if "youtube.com" not in url.lower() and "youtu.be" not in url.lower():
        raise DownloadError("URL does not look like YouTube.")

    return download_with_ytdlp(
        url,
        output_dir,
        prefix="yt",
        error_label="YouTube download failed",
    )
