#!/usr/bin/env python3
"""Download video from a Threads post URL."""

from __future__ import annotations

import re
import urllib.error
from pathlib import Path

from common import (
    OUTPUT_DIR,
    THREADS_APP_ID,
    DownloadError,
    best_video_url,
    fetch,
    make_opener,
    media_items,
    parse_json_object,
    save_videos,
    walk,
)

THREADS_URL_RE = re.compile(
    r"https?://(?:www\.)?threads\.(?:com|net)/\S+",
    re.IGNORECASE,
)


def extract_threads_url(text: str) -> str | None:
    match = THREADS_URL_RE.search(text)
    if not match:
        return None
    return match.group(0).rstrip(").,]}>\"'")


def extract_post_id(url: str) -> str | None:
    for pattern in (
        r"/post/([^/?#]+)",
        r"/t/([^/?#]+)",
        r"/share/([^/?#]+)",
    ):
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def find_posts(html: str, post_id: str | None) -> list[dict]:
    scripts = re.findall(
        r"<script[^>]*\sdata-sjs[^>]*>(.*?)</script>",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    found: list[dict] = []
    seen: set[str] = set()

    for script in scripts:
        if "RelayPrefetchedStreamCache" not in script:
            continue
        if post_id and post_id not in script and "video_versions" not in script:
            continue

        pos = 0
        while True:
            idx = script.find('"result":', pos)
            if idx < 0:
                break
            brace = script.find("{", idx + len('"result":') - 1)
            data = parse_json_object(script, brace)
            if data is not None:
                for node in walk(data):
                    if not isinstance(node, dict):
                        continue
                    code = node.get("code")
                    if not isinstance(code, str):
                        continue
                    if not (node.get("video_versions") or node.get("carousel_media")):
                        continue
                    if code in seen:
                        continue
                    if post_id and code != post_id:
                        continue
                    seen.add(code)
                    found.append(node)
            pos = idx + len('"result":')

    if not found and post_id:
        return find_posts(html, None)
    return found


def download_threads(url: str, output_dir: Path = OUTPUT_DIR) -> list[Path]:
    """Download all videos from a Threads post. Returns saved file paths."""
    if "threads." not in url.lower():
        raise DownloadError("URL does not look like Threads.")

    opener = make_opener()
    fetch(opener, "https://www.threads.com/", app_id=THREADS_APP_ID)

    try:
        final_url, html = fetch(
            opener,
            url,
            referer="https://www.threads.com/",
            app_id=THREADS_APP_ID,
        )
    except urllib.error.HTTPError as exc:
        raise DownloadError(f"HTTP error: {exc}") from exc
    except urllib.error.URLError as exc:
        raise DownloadError(f"Network error: {exc}") from exc

    post_id = extract_post_id(final_url) or extract_post_id(url)
    canonical = re.search(r"/post/([^/?#]+)", final_url) or re.search(
        r"/t/([^/?#]+)", final_url
    )
    if canonical:
        post_id = canonical.group(1)

    posts = find_posts(html, post_id)
    if not posts:
        raise DownloadError(
            "Could not find video data on the page. "
            "Post may be private, deleted, or Threads blocked the request."
        )

    post = next((p for p in posts if p.get("code") == post_id), posts[0])
    username = ((post.get("user") or {}).get("username")) or "unknown"
    code = post.get("code") or post_id or "post"
    items = media_items(post)
    video_urls = [u for u in (best_video_url(item) for item in items) if u]

    return save_videos(
        opener,
        video_urls,
        output_dir=output_dir,
        username=username,
        code=str(code),
        referer="https://www.threads.com/",
        origin="https://www.threads.com",
        prefix="threads",
    )
