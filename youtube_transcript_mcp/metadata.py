"""Video metadata: chapters, description, available caption languages.

Chapters are the highest-value field here. A 2-hour lecture with 30 chapters is
navigable; the same lecture as 2,955 caption fragments is not. Everything that
makes the transcript readable — headings, deep links, per-chapter fetching —
hangs off this.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field

from .urls import canonical_url

log = logging.getLogger(__name__)

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


def fetch_video_info(video_id: str, *, use_cache: bool = True) -> VideoInfo:
    import yt_dlp

    if use_cache and (hit := _CACHE.get(video_id)):
        cached_at, info = hit
        if time.time() - cached_at < _CACHE_TTL:
            return info

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

    info = VideoInfo(
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
