#!/usr/bin/env python3
"""Download video from a TikTok URL via yt-dlp."""

from __future__ import annotations

import re
from pathlib import Path

from common import OUTPUT_DIR, DownloadError
from ytdlp_helper import download_with_ytdlp

# Full video links + share short links (vm/vt/t/)
TIKTOK_URL_RE = re.compile(
    r"https?://(?:(?:www|m)\.)?tiktok\.com/(?:@[\w.\-]+/video/\d+|t/[\w]+)[^\s]*"
    r"|https?://(?:vm|vt)\.tiktok\.com/[\w]+[^\s]*",
    re.IGNORECASE,
)


def extract_tiktok_url(text: str) -> str | None:
    match = TIKTOK_URL_RE.search(text)
    if not match:
        return None
    return match.group(0).rstrip(").,]}>\"'")


def download_tiktok(url: str, output_dir: Path = OUTPUT_DIR) -> list[Path]:
    """Download a TikTok video. Returns saved file paths."""
    if "tiktok.com" not in url.lower():
        raise DownloadError("URL does not look like TikTok.")

    return download_with_ytdlp(
        url,
        output_dir,
        prefix="tt",
        error_label="TikTok download failed",
    )
