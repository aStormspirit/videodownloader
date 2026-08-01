#!/usr/bin/env python3
"""Download video from an Instagram post / reel URL."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
from pathlib import Path

from common import (
    INSTAGRAM_APP_ID,
    OUTPUT_DIR,
    DownloadError,
    best_video_url,
    cookie_value,
    fetch,
    make_opener,
    media_items,
    parse_json_object,
    post_form,
    save_videos,
    walk,
)

# Public GraphQL doc used by Instagram web for shortcode media info
GRAPHQL_DOC_ID = "24368985919464652"

INSTAGRAM_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:instagram\.com|instagr\.am)/\S+",
    re.IGNORECASE,
)

SHORTCODE_RE = re.compile(
    r"(?:instagram\.com|instagr\.am)/(?:[^/]+/)?(?:reel|reels|p|tv)/([^/?#]+)",
    re.IGNORECASE,
)


def extract_instagram_url(text: str) -> str | None:
    match = INSTAGRAM_URL_RE.search(text)
    if not match:
        return None
    return match.group(0).rstrip(").,]}>\"'")


def extract_shortcode(url: str) -> str | None:
    clean = url.split("?")[0].split("#")[0]
    match = SHORTCODE_RE.search(clean)
    return match.group(1) if match else None


def _item_from_graphql(data: dict, shortcode: str) -> dict | None:
    for node in walk(data):
        if not isinstance(node, dict):
            continue
        items = node.get("items")
        if isinstance(items, list) and items:
            for item in items:
                if not isinstance(item, dict):
                    continue
                if item.get("code") == shortcode or shortcode is None:
                    if item.get("video_versions") or item.get("carousel_media"):
                        return item
            first = items[0]
            if isinstance(first, dict) and (
                first.get("video_versions") or first.get("carousel_media")
            ):
                return first
        code = node.get("code")
        if code == shortcode and (node.get("video_versions") or node.get("carousel_media")):
            return node
    return None


def _fetch_via_graphql(
    opener,
    shortcode: str,
) -> dict | None:
    csrf = cookie_value(opener, "csrftoken") or "missing"
    variables = json.dumps({"shortcode": shortcode}, separators=(",", ":"))
    body = urllib.parse.urlencode(
        {"variables": variables, "doc_id": GRAPHQL_DOC_ID}
    ).encode()

    try:
        data = post_form(
            opener,
            "https://www.instagram.com/graphql/query",
            body,
            referer=f"https://www.instagram.com/reel/{shortcode}/",
            app_id=INSTAGRAM_APP_ID,
            extra_headers={
                "X-Csrftoken": csrf,
                "X-Requested-With": "XMLHttpRequest",
                "X-Asbd-Id": "359341",
            },
        )
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError):
        return None

    return _item_from_graphql(data, shortcode)


def _fetch_via_html(opener, url: str, shortcode: str) -> dict | None:
    try:
        _, html = fetch(
            opener,
            url,
            referer="https://www.instagram.com/",
            app_id=INSTAGRAM_APP_ID,
        )
    except (urllib.error.HTTPError, urllib.error.URLError):
        return None

    # Prefer exact shortcode matches with video_versions
    for node in walk(_extract_embedded_json(html)):
        if not isinstance(node, dict):
            continue
        if node.get("code") == shortcode and (
            node.get("video_versions") or node.get("carousel_media")
        ):
            return node

    for node in walk(_extract_embedded_json(html)):
        if not isinstance(node, dict):
            continue
        if node.get("video_versions") or node.get("carousel_media"):
            if shortcode and node.get("code") not in (None, shortcode):
                continue
            return node
    return None


def _extract_embedded_json(html: str) -> list[object]:
    blobs: list[object] = []

    # application/json / ld+json / data-sjs scripts
    for script in re.findall(
        r"<script[^>]*>(.*?)</script>",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    ):
        if "video_versions" not in script and "xdt_api__v1__media" not in script:
            continue
        # Try whole-script JSON
        stripped = script.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                blobs.append(json.loads(stripped))
                continue
            except json.JSONDecodeError:
                pass
        # Scan for JSON objects that mention video_versions
        pos = 0
        while True:
            idx = script.find("video_versions", pos)
            if idx < 0:
                break
            brace = script.rfind("{", 0, idx)
            if brace >= 0:
                for start in range(brace, max(-1, brace - 5000), -1):
                    if script[start] != "{":
                        continue
                    data = parse_json_object(script, start)
                    if data is not None:
                        blobs.append(data)
                        break
            pos = idx + len("video_versions")

    return blobs


def download_instagram(url: str, output_dir: Path = OUTPUT_DIR) -> list[Path]:
    """Download all videos from an Instagram post/reel. Returns saved file paths."""
    if "instagram." not in url.lower() and "instagr.am" not in url.lower():
        raise DownloadError("URL does not look like Instagram.")

    shortcode = extract_shortcode(url)
    if not shortcode:
        raise DownloadError(
            "Could not parse Instagram shortcode. "
            "Use a /reel/, /p/, or /tv/ link."
        )

    opener = make_opener()
    try:
        fetch(opener, "https://www.instagram.com/", app_id=INSTAGRAM_APP_ID)
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise DownloadError(f"Network error warming up Instagram session: {exc}") from exc

    item = _fetch_via_graphql(opener, shortcode)
    if item is None:
        # Normalize to a canonical page URL for HTML scrape
        page_url = f"https://www.instagram.com/reel/{shortcode}/"
        if "/p/" in url:
            page_url = f"https://www.instagram.com/p/{shortcode}/"
        item = _fetch_via_html(opener, page_url, shortcode)

    if item is None:
        raise DownloadError(
            "Could not find video data. "
            "Post may be private, deleted, or Instagram blocked the request."
        )

    username = ((item.get("user") or {}).get("username")) or "unknown"
    code = item.get("code") or shortcode
    items = media_items(item)
    video_urls = [u for u in (best_video_url(m) for m in items) if u]

    return save_videos(
        opener,
        video_urls,
        output_dir=output_dir,
        username=username,
        code=str(code),
        referer="https://www.instagram.com/",
        origin="https://www.instagram.com",
        prefix="ig",
    )
