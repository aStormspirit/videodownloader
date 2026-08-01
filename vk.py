#!/usr/bin/env python3
"""Download video from a VK (VKontakte) URL via yt-dlp."""

from __future__ import annotations

import re
from pathlib import Path

from common import OUTPUT_DIR, DownloadError
from ytdlp_helper import download_with_ytdlp

# vk.com / vk.ru / vkvideo.ru — video, clip, embed, and z=video… deep links
VK_URL_RE = re.compile(
    r"https?://(?:(?:m|www|new)\.)?"
    r"(?:"
    r"vk\.(?:com|ru)/(?:video|clip)-?\d+_\d+[^\s]*"
    r"|vk\.(?:com|ru)/video_ext\.php\?[^\s]+"
    r"|vk\.(?:com|ru)/clips?-?\d+[^\s]*[?&]z=(?:video|clip)-?\d+_\d+[^\s]*"
    r"|vk\.(?:com|ru)/[^\s]*[?&]z=(?:video|clip)-?\d+_\d+[^\s]*"
    r"|vkvideo\.ru/(?:video|clip)-?\d+_\d+[^\s]*"
    r")",
    re.IGNORECASE,
)


def extract_vk_url(text: str) -> str | None:
    match = VK_URL_RE.search(text)
    if not match:
        return None
    return match.group(0).rstrip(").,]}>\"'")


def download_vk(url: str, output_dir: Path = OUTPUT_DIR) -> list[Path]:
    """Download a VK video / clip. Returns saved file paths."""
    lower = url.lower()
    if not any(host in lower for host in ("vk.com", "vk.ru", "vkvideo.ru")):
        raise DownloadError("URL does not look like VK.")

    return download_with_ytdlp(
        url,
        output_dir,
        prefix="vk",
        error_label="VK download failed",
    )
