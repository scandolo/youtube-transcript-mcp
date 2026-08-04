"""Transcript fetching, as an ordered chain of backends.

Order matters and reflects cost, not preference alone:

1. ``youtube-transcript-api`` — one request to the caption endpoint. Fastest.
2. ``yt-dlp`` — heavier, but survives cases where (1) sees no tracks.
3. Groq Whisper — the only option when captions are disabled entirely. Costs
   money and downloads audio, so it never runs unless the first two fail.

The first backend to return segments wins. Every attempt is recorded on the
result so ``doctor``-style debugging doesn't need log spelunking.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from .urls import canonical_url

log = logging.getLogger(__name__)

#: Groq rejects uploads above this; chunking with ffmpeg would lift it.
_WHISPER_MAX_BYTES = 24 * 1024 * 1024
_GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
_GROQ_MODEL = "whisper-large-v3-turbo"


class TranscriptError(RuntimeError):
    """No backend could produce a transcript."""


@dataclass
class Segment:
    start: float
    duration: float
    text: str


@dataclass
class Transcript:
    video_id: str
    segments: list[Segment]
    source: str
    language: str
    is_generated: bool
    title: str | None = None
    channel: str | None = None
    duration: float | None = None
    attempts: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.segments)


def _proxy() -> str | None:
    return os.environ.get("YTM_PROXY") or None


def _lang_matches(key: str, wanted: list[str]) -> bool:
    """`en` should match `en`, `en-US`, `en-orig` and yt-dlp's `a.en`."""
    normalized = key.lower().removeprefix("a.")
    return any(normalized == w.lower() or normalized.startswith(w.lower() + "-") for w in wanted)


# --------------------------------------------------------------------------
# Backend 1 — youtube-transcript-api
# --------------------------------------------------------------------------


def _via_transcript_api(video_id: str, languages: list[str]) -> Transcript | None:
    from youtube_transcript_api import YouTubeTranscriptApi

    proxy_config = None
    if proxy := _proxy():
        from youtube_transcript_api.proxies import GenericProxyConfig

        proxy_config = GenericProxyConfig(http_url=proxy, https_url=proxy)

    api = YouTubeTranscriptApi(proxy_config=proxy_config)
    fetched = api.fetch(video_id, languages=languages)

    segments = [
        Segment(start=s.start, duration=s.duration, text=s.text.strip())
        for s in fetched.snippets
        if s.text.strip()
    ]
    if not segments:
        return None

    return Transcript(
        video_id=video_id,
        segments=segments,
        source="youtube-transcript-api",
        language=fetched.language_code,
        is_generated=fetched.is_generated,
    )


# --------------------------------------------------------------------------
# Backend 2 — yt-dlp caption tracks
# --------------------------------------------------------------------------


def _parse_json3(payload: dict) -> list[Segment]:
    segments = []
    for event in payload.get("events", []):
        pieces = event.get("segs")
        if not pieces:
            continue
        text = "".join(p.get("utf8", "") for p in pieces).strip()
        if not text:
            continue
        segments.append(
            Segment(
                start=event.get("tStartMs", 0) / 1000,
                duration=event.get("dDurationMs", 0) / 1000,
                text=text,
            )
        )
    return segments


def _pick_track(tracks: dict, languages: list[str]) -> tuple[str, str] | None:
    """Return (language_code, json3_url) for the best matching caption track."""
    ordered = [k for k in tracks if _lang_matches(k, languages)] or list(tracks)
    for key in ordered:
        for fmt in tracks[key]:
            if fmt.get("ext") == "json3" and fmt.get("url"):
                return key, fmt["url"]
    return None


def _via_yt_dlp(video_id: str, languages: list[str]) -> Transcript | None:
    import yt_dlp

    opts = {"skip_download": True, "quiet": True, "no_warnings": True}
    if proxy := _proxy():
        opts["proxy"] = proxy

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(canonical_url(video_id), download=False)

    manual = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}

    is_generated = False
    picked = _pick_track(manual, languages)
    if not picked:
        picked = _pick_track(auto, languages)
        is_generated = True
    if not picked:
        return None

    language, url = picked
    client_kwargs = {"timeout": 30, "follow_redirects": True}
    if proxy := _proxy():
        client_kwargs["proxy"] = proxy
    with httpx.Client(**client_kwargs) as client:
        response = client.get(url)
        response.raise_for_status()
        segments = _parse_json3(response.json())

    if not segments:
        return None

    return Transcript(
        video_id=video_id,
        segments=segments,
        source="yt-dlp",
        language=language.removeprefix("a."),
        is_generated=is_generated,
        title=info.get("title"),
        channel=info.get("uploader") or info.get("channel"),
        duration=info.get("duration"),
    )


# --------------------------------------------------------------------------
# Backend 3 — Groq Whisper on the audio track
# --------------------------------------------------------------------------


def _via_whisper(video_id: str, languages: list[str]) -> Transcript | None:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None

    with tempfile.TemporaryDirectory() as tmp:
        opts = {
            "format": "bestaudio[ext=m4a]/bestaudio",
            "outtmpl": str(Path(tmp) / "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
        }
        if proxy := _proxy():
            opts["proxy"] = proxy

        import yt_dlp

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(canonical_url(video_id), download=True)

        audio = next((p for p in Path(tmp).iterdir() if p.is_file()), None)
        if audio is None:
            return None

        size = audio.stat().st_size
        if size > _WHISPER_MAX_BYTES:
            raise TranscriptError(
                f"Audio is {size / 1e6:.0f}MB, above the {_WHISPER_MAX_BYTES / 1e6:.0f}MB "
                "Whisper upload limit. Splitting long audio with ffmpeg is not implemented yet."
            )

        with httpx.Client(timeout=300) as client:
            response = client.post(
                _GROQ_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (audio.name, audio.read_bytes())},
                data={
                    "model": _GROQ_MODEL,
                    "response_format": "verbose_json",
                    "language": languages[0] if languages else "en",
                },
            )
            response.raise_for_status()
            payload = response.json()

    segments = [
        Segment(
            start=float(s.get("start", 0)),
            duration=float(s.get("end", 0)) - float(s.get("start", 0)),
            text=s.get("text", "").strip(),
        )
        for s in payload.get("segments", [])
        if s.get("text", "").strip()
    ]
    if not segments:
        return None

    return Transcript(
        video_id=video_id,
        segments=segments,
        source=f"groq:{_GROQ_MODEL}",
        language=payload.get("language", languages[0] if languages else "en"),
        is_generated=True,
        title=info.get("title"),
        channel=info.get("uploader") or info.get("channel"),
        duration=info.get("duration"),
    )


# --------------------------------------------------------------------------


_BACKENDS = (
    ("youtube-transcript-api", _via_transcript_api),
    ("yt-dlp", _via_yt_dlp),
    ("whisper", _via_whisper),
)


def _enrich(transcript: Transcript) -> None:
    """Fill in metadata the winning backend didn't carry.

    Backend 1 returns captions only. Duration matters beyond cosmetics — it
    selects HH:MM:SS over MM:SS timecodes, and without it a 3-hour video renders
    1:01:01 as "01:01". Derive it from the segments rather than paying for a
    second heavy call; title/channel come from oEmbed, which is cheap and
    optional.
    """
    if transcript.duration is None and transcript.segments:
        last = transcript.segments[-1]
        transcript.duration = round(last.start + last.duration, 2)

    if transcript.title is not None:
        return

    try:
        client_kwargs = {"timeout": 5, "follow_redirects": True}
        if proxy := _proxy():
            client_kwargs["proxy"] = proxy
        with httpx.Client(**client_kwargs) as client:
            response = client.get(
                "https://www.youtube.com/oembed",
                params={"url": canonical_url(transcript.video_id), "format": "json"},
            )
            response.raise_for_status()
            payload = response.json()
        transcript.title = payload.get("title")
        transcript.channel = transcript.channel or payload.get("author_name")
    except Exception as exc:  # metadata is a nicety, never fail the request for it
        log.debug("oembed lookup failed for %s: %s", transcript.video_id, exc)


def fetch_transcript(video_id: str, languages: list[str] | None = None) -> Transcript:
    """Walk the backend chain and return the first transcript produced."""
    languages = languages or ["en"]
    attempts: list[str] = []

    for name, backend in _BACKENDS:
        try:
            result = backend(video_id, languages)
        except Exception as exc:  # a dead backend must not sink the chain
            attempts.append(f"{name}: {type(exc).__name__}: {exc}")
            log.warning("backend %s failed for %s: %s", name, video_id, exc)
            continue

        if result is not None:
            result.attempts = attempts
            _enrich(result)
            return result
        attempts.append(f"{name}: no captions found")

    raise TranscriptError(
        "Could not get a transcript for "
        f"{video_id}. Attempts:\n  " + "\n  ".join(attempts or ["none"])
    )
