#!/usr/bin/env python3
"""CLI: download video from supported platforms."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import OUTPUT_DIR, DownloadError
from instagram import download_instagram, extract_instagram_url
from threads import download_threads, extract_threads_url
from tiktok import download_tiktok, extract_tiktok_url
from vk import download_vk, extract_vk_url
from youtube import download_youtube, extract_youtube_url


def detect_and_download(url: str, output_dir: Path) -> list[Path]:
    if extract_threads_url(url):
        return download_threads(url, output_dir)
    if extract_instagram_url(url):
        return download_instagram(url, output_dir)
    if extract_youtube_url(url):
        return download_youtube(url, output_dir)
    if extract_vk_url(url):
        return download_vk(url, output_dir)
    if extract_tiktok_url(url):
        return download_tiktok(url, output_dir)
    raise DownloadError(
        "Unsupported URL. Send a Threads, Instagram, YouTube, VK, or TikTok link."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download video from Threads, Instagram, YouTube, VK, or TikTok."
    )
    parser.add_argument("url", nargs="?", help="Video post URL")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Directory to save videos (default: downloads)",
    )
    args = parser.parse_args()

    url = (args.url or "").strip()
    if not url:
        print(
            "Usage: python main.py <threads|instagram|youtube|vk|tiktok-url>",
            file=sys.stderr,
        )
        return 1

    try:
        saved = detect_and_download(url, args.output_dir)
    except DownloadError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print("Saved:")
    for path in saved:
        print(f"  {path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
