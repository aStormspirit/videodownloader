#!/usr/bin/env python3
"""Shared helpers for Threads / Instagram downloaders."""

from __future__ import annotations

import http.cookiejar
import json
import re
import urllib.request
from pathlib import Path

OUTPUT_DIR = Path("downloads")

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Meta web app IDs
THREADS_APP_ID = "238260118697367"
INSTAGRAM_APP_ID = "936619743392459"


class DownloadError(Exception):
    """Raised when a video cannot be downloaded."""


def make_opener() -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def browser_headers(
    *,
    referer: str | None = None,
    app_id: str | None = None,
    content_type: str | None = None,
) -> dict[str, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Linux"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }
    if app_id:
        headers["X-Ig-App-Id"] = app_id
    if content_type:
        headers["Content-Type"] = content_type
    if referer:
        headers["Referer"] = referer
        headers["Sec-Fetch-Site"] = "same-origin"
    else:
        headers["Sec-Fetch-Site"] = "none"
    return headers


def fetch(
    opener: urllib.request.OpenerDirector,
    url: str,
    *,
    referer: str | None = None,
    app_id: str | None = None,
) -> tuple[str, str]:
    req = urllib.request.Request(url, headers=browser_headers(referer=referer, app_id=app_id))
    with opener.open(req, timeout=45) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.geturl(), raw.decode(charset, errors="replace")


def post_form(
    opener: urllib.request.OpenerDirector,
    url: str,
    data: bytes,
    *,
    referer: str | None = None,
    app_id: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> dict:
    headers = browser_headers(
        referer=referer,
        app_id=app_id,
        content_type="application/x-www-form-urlencoded",
    )
    headers["Accept"] = "*/*"
    headers["Sec-Fetch-Dest"] = "empty"
    headers["Sec-Fetch-Mode"] = "cors"
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with opener.open(req, timeout=45) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
        return json.loads(raw.decode(charset, errors="replace"))


def cookie_value(opener: urllib.request.OpenerDirector, name: str) -> str | None:
    for handler in opener.handlers:
        jar = getattr(handler, "cookiejar", None)
        if jar is None:
            continue
        for cookie in jar:
            if cookie.name == name:
                return cookie.value
    return None


def parse_json_object(text: str, start: int) -> object | None:
    if start >= len(text) or text[start] != "{":
        return None
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : index + 1])
                except json.JSONDecodeError:
                    return None
    return None


def walk(obj: object):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from walk(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from walk(item)


def media_items(post: dict) -> list[dict]:
    carousel = post.get("carousel_media")
    if isinstance(carousel, list) and carousel:
        return [item for item in carousel if isinstance(item, dict)]
    return [post]


def best_video_url(media: dict) -> str | None:
    versions = media.get("video_versions")
    if not isinstance(versions, list) or not versions:
        return None

    def score(item: dict) -> tuple[int, int]:
        return (int(item.get("height") or 0), int(item.get("width") or 0))

    ranked = sorted(
        (item for item in versions if isinstance(item, dict) and item.get("url")),
        key=score,
        reverse=True,
    )
    return ranked[0]["url"] if ranked else None


def download_file(
    opener: urllib.request.OpenerDirector,
    url: str,
    dest: Path,
    *,
    referer: str,
    origin: str,
) -> None:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Referer": referer,
            "Origin": origin,
        },
    )
    with opener.open(req, timeout=120) as resp, dest.open("wb") as out:
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            out.write(chunk)


def safe_name(value: str, fallback: str = "video") -> str:
    cleaned = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE).strip("._")
    return cleaned or fallback


def save_videos(
    opener: urllib.request.OpenerDirector,
    video_urls: list[str],
    *,
    output_dir: Path,
    username: str,
    code: str,
    referer: str,
    origin: str,
    prefix: str,
) -> list[Path]:
    if not video_urls:
        raise DownloadError("Post has no downloadable video.")

    output_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for index, video_url in enumerate(video_urls, start=1):
        suffix = f"_{index}" if len(video_urls) > 1 else ""
        dest = (
            output_dir
            / f"{prefix}_{safe_name(username)}_{safe_name(str(code))}{suffix}.mp4"
        )
        try:
            download_file(opener, video_url, dest, referer=referer, origin=origin)
        except Exception as exc:  # noqa: BLE001
            raise DownloadError(f"Failed to download video: {exc}") from exc
        saved.append(dest)
    return saved
