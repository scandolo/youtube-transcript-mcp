"""Video metadata: chapters, description, available caption languages.

Chapters are the highest-value field here. A 2-hour lecture with 30 chapters is
navigable; the same lecture as 2,955 caption fragments is not. Everything that
makes the transcript readable — headings, deep links, per-chapter fetching —
hangs off this.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field

import httpx

from .env import api_referer, proxy
from .urls import canonical_url

log = logging.getLogger(__name__)

_DATA_API_URL = "https://www.googleapis.com/youtube/v3/videos"

#: A description chapter line: "12:34 Title" or "1:02:03 Title".
_CHAPTER_LINE = re.compile(r"^\s*(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\s+(.{1,120})$", re.M)

_ISO_DURATION = re.compile(
    r"^P(?:(?P<days>\d+)D)?T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?$"
)

#: yt-dlp metadata costs ~3s. Agents typically call info then transcript for the
#: same video, so a short TTL cache turns the second call free.
_CACHE: dict[str, tuple[float, "VideoInfo"]] = {}
_CACHE_TTL = 900


@dataclass
class Chapter:
    index: int
    title: str
    start: float
    end: float | None = None


@dataclass
class VideoInfo:
    video_id: str
    title: str | None = None
    channel: str | None = None
    duration: float | None = None
    upload_date: str | None = None
    view_count: int | None = None
    description: str = ""
    chapters: list[Chapter] = field(default_factory=list)
    manual_caption_languages: list[str] = field(default_factory=list)
    auto_caption_languages: list[str] = field(default_factory=list)


def deep_link(video_id: str, seconds: float) -> str:
    """A URL that opens the video at this moment — lets an agent cite precisely."""
    return f"https://youtu.be/{video_id}?t={int(seconds)}"


def _iso_duration_seconds(value: str) -> float | None:
    match = _ISO_DURATION.match(value or "")
    if not match:
        return None
    parts = {k: int(v) for k, v in match.groupdict(default="0").items()}
    return float(
        parts["days"] * 86400 + parts["hours"] * 3600 + parts["minutes"] * 60 + parts["seconds"]
    )


def parse_chapters(description: str) -> list[Chapter]:
    """Recover chapters from the timestamp lines in a video description.

    This is where YouTube itself gets them, so the result matches the official
    chapter list. Lines must step forward in time and start at zero, which
    filters out stray timestamps elsewhere in the description.
    """
    candidates = []
    for hours, minutes, seconds, title in _CHAPTER_LINE.findall(description or ""):
        start = int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds)
        candidates.append((start, title.strip(" -–—:\t")))

    if not candidates or candidates[0][0] != 0:
        return []

    chapters: list[Chapter] = []
    for start, title in candidates:
        if chapters and start <= chapters[-1].start:
            continue  # not moving forward — not part of the chapter list
        chapters.append(Chapter(index=len(chapters) + 1, title=title or "Untitled", start=start))

    return chapters if len(chapters) > 1 else []


def _via_data_api(video_id: str) -> VideoInfo | None:
    """Metadata via the official Data API.

    Key-authenticated, so unlike the caption endpoints it is not blocked on
    datacenter IPs — which is what makes cloud hosting viable at all.
    """
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        return None

    headers = {}
    if referer := api_referer():
        headers["Referer"] = referer

    kwargs = {"timeout": 20}
    if p := proxy():
        kwargs["proxy"] = p

    with httpx.Client(**kwargs) as client:
        response = client.get(
            _DATA_API_URL,
            params={"part": "snippet,contentDetails", "id": video_id, "key": key},
            headers=headers,
        )
        response.raise_for_status()
        payload = response.json()

    items = payload.get("items") or []
    if not items:
        return None

    snippet = items[0].get("snippet") or {}
    details = items[0].get("contentDetails") or {}
    description = snippet.get("description") or ""

    return VideoInfo(
        video_id=video_id,
        title=snippet.get("title"),
        channel=snippet.get("channelTitle"),
        duration=_iso_duration_seconds(details.get("duration", "")),
        upload_date=(snippet.get("publishedAt") or "")[:10].replace("-", "") or None,
        description=description,
        chapters=parse_chapters(description),
    )


def _via_yt_dlp(video_id: str) -> VideoInfo:
    import yt_dlp

    opts = {"skip_download": True, "quiet": True, "no_warnings": True}
    if proxy := os.environ.get("YTM_PROXY"):
        opts["proxy"] = proxy

    with yt_dlp.YoutubeDL(opts) as ydl:
        raw = ydl.extract_info(canonical_url(video_id), download=False)

    chapters = []
    for i, chapter in enumerate(raw.get("chapters") or []):
        chapters.append(
            Chapter(
                index=i + 1,
                title=chapter.get("title") or f"Chapter {i + 1}",
                start=float(chapter.get("start_time", 0)),
                end=float(chapter["end_time"]) if chapter.get("end_time") else None,
            )
        )

    return VideoInfo(
        video_id=video_id,
        title=raw.get("title"),
        channel=raw.get("channel") or raw.get("uploader"),
        duration=raw.get("duration"),
        upload_date=raw.get("upload_date"),
        view_count=raw.get("view_count"),
        description=raw.get("description") or "",
        chapters=chapters,
        manual_caption_languages=sorted(raw.get("subtitles") or {}),
        auto_caption_languages=sorted(raw.get("automatic_captions") or {}),
    )


def fetch_video_info(video_id: str, *, use_cache: bool = True) -> VideoInfo:
    """Video metadata, preferring whichever source can actually reach YouTube.

    The Data API goes first when a key is configured: it is key-authenticated
    and therefore works from datacenter IPs, where yt-dlp is blocked. yt-dlp
    stays as the fallback because it needs no key and reports caption languages
    the Data API doesn't expose.
    """
    if use_cache and (hit := _CACHE.get(video_id)):
        cached_at, info = hit
        if time.time() - cached_at < _CACHE_TTL:
            return info

    info: VideoInfo | None = None
    errors = []

    for name, backend in (("data-api", _via_data_api), ("yt-dlp", _via_yt_dlp)):
        try:
            info = backend(video_id)
        except Exception as exc:
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
            log.warning("metadata backend %s failed for %s: %s", name, video_id, exc)
            continue
        if info is not None:
            break

    if info is None:
        raise RuntimeError(
            f"No metadata backend could describe {video_id}. " + "; ".join(errors or ["no backends"])
        )

    _CACHE[video_id] = (time.time(), info)
    return info


def find_chapter(info: VideoInfo, wanted: str) -> Chapter | None:
    """Resolve a chapter by 1-based index or case-insensitive title substring."""
    wanted = wanted.strip()
    if not info.chapters:
        return None

    if wanted.isdigit():
        index = int(wanted)
        return next((c for c in info.chapters if c.index == index), None)

    lowered = wanted.lower()
    matches = [c for c in info.chapters if lowered in c.title.lower()]
    return matches[0] if matches else None


def chapter_bounds(info: VideoInfo, chapter: Chapter) -> tuple[float, float]:
    """Start/end for a chapter, falling back to the next chapter's start."""
    if chapter.end is not None:
        return chapter.start, chapter.end
    later = [c.start for c in info.chapters if c.start > chapter.start]
    end = min(later) if later else (info.duration or float("inf"))
    return chapter.start, end
