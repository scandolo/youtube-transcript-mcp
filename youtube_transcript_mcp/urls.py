"""YouTube URL → video id."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")

_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}

# /shorts/<id>, /embed/<id>, /live/<id>, /v/<id>
_PATH_PREFIXES = ("shorts", "embed", "live", "v")


class NotAYouTubeURL(ValueError):
    """The input is neither a YouTube URL nor a bare video id."""


def extract_video_id(value: str) -> str:
    """Accept a YouTube URL in any of its shapes, or a bare 11-char video id."""
    value = value.strip()
    if VIDEO_ID.match(value):
        return value

    if "//" not in value:
        value = "https://" + value

    parsed = urlparse(value)
    host = parsed.netloc.lower().split(":")[0]
    parts = [p for p in parsed.path.split("/") if p]

    if host in ("youtu.be", "www.youtu.be"):
        if parts and VIDEO_ID.match(parts[0]):
            return parts[0]
        raise NotAYouTubeURL(f"No video id in short URL: {value}")

    if host in _HOSTS:
        if parts and parts[0] == "watch":
            candidate = parse_qs(parsed.query).get("v", [None])[0]
            if candidate and VIDEO_ID.match(candidate):
                return candidate
        if len(parts) >= 2 and parts[0] in _PATH_PREFIXES and VIDEO_ID.match(parts[1]):
            return parts[1]
        raise NotAYouTubeURL(f"No video id found in: {value}")

    raise NotAYouTubeURL(f"Not a YouTube URL: {value}")


def canonical_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"
