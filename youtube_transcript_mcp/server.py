"""The MCP server.

Two tools, deliberately shaped around how an agent actually works through a
video: orient first (`youtube_video_info` — cheap, chapters and description),
then drill in (`youtube_transcript` — a chapter, a keyword search, or the lot).

Identity is checked in middleware rather than inside each tool, so a tool added
later cannot accidentally ship unprotected. The check fails closed: if auth is
enabled and no identity can be resolved, the call is refused.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext

from .formatting import build_response, timecode
from .metadata import chapter_bounds, deep_link, fetch_video_info, find_chapter
from .transcript import TranscriptError, fetch_transcript
from .urls import NotAYouTubeURL, extract_video_id

load_dotenv()

logging.basicConfig(level=os.environ.get("YTM_LOG_LEVEL", "INFO"))
log = logging.getLogger("youtube-transcript-mcp")

MAX_CHARS_CEILING = 200_000
DESCRIPTION_LIMIT = 2_000


def _allowed_identities() -> set[str]:
    raw = os.environ.get("YTM_ALLOWED_USERS", "")
    return {u.strip().lower() for u in raw.split(",") if u.strip()}


class AllowlistMiddleware(Middleware):
    """Refuse tool calls from anyone outside YTM_ALLOWED_USERS."""

    def __init__(self, allowed: set[str]) -> None:
        self.allowed = allowed

    @staticmethod
    def _identity() -> str | None:
        from fastmcp.server.dependencies import get_access_token

        try:
            token = get_access_token()
        except Exception:
            return None
        if token is None:
            return None

        claims = getattr(token, "claims", None) or {}
        for key in ("login", "email", "sub"):
            if value := claims.get(key):
                return str(value).lower()
        return None

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        identity = self._identity()
        if identity is None:
            raise ToolError("Not authorized: no verified identity on this request.")
        if identity not in self.allowed:
            log.warning("rejected tool call from %s", identity)
            raise ToolError(f"Not authorized: {identity} is not on the allowlist.")
        return await call_next(context)


def _build_auth():
    """Construct the OAuth provider named by YTM_AUTH_PROVIDER, or None."""
    provider = os.environ.get("YTM_AUTH_PROVIDER", "none").strip().lower()
    if provider in ("", "none"):
        return None

    base_url = os.environ.get("YTM_BASE_URL")
    if not base_url:
        raise SystemExit("YTM_BASE_URL must be set (public https URL) when auth is enabled.")

    if provider == "github":
        from fastmcp.server.auth.providers.github import GitHubProvider

        return GitHubProvider(
            client_id=os.environ["GITHUB_CLIENT_ID"],
            client_secret=os.environ["GITHUB_CLIENT_SECRET"],
            base_url=base_url,
        )

    if provider == "google":
        from fastmcp.server.auth.providers.google import GoogleProvider

        return GoogleProvider(
            client_id=os.environ["GOOGLE_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
            base_url=base_url,
        )

    raise SystemExit(f"Unknown YTM_AUTH_PROVIDER: {provider!r} (use github, google or none)")


_auth = _build_auth()

mcp = FastMCP(name="youtube-transcript", auth=_auth)

if _auth is not None:
    _allowed = _allowed_identities()
    if not _allowed:
        raise SystemExit("Auth is enabled but YTM_ALLOWED_USERS is empty — refusing to start open.")
    mcp.add_middleware(AllowlistMiddleware(_allowed))
    log.info("allowlist active for %d identity(ies)", len(_allowed))
else:
    log.warning("running WITHOUT authentication — local stdio use only")


def _resolve(url: str) -> str:
    try:
        return extract_video_id(url)
    except NotAYouTubeURL as exc:
        raise ToolError(str(exc)) from exc


def _safe_info(video_id: str):
    """Metadata is a quality upgrade, not a dependency — degrade if it fails."""
    try:
        return fetch_video_info(video_id)
    except Exception as exc:
        log.warning("metadata lookup failed for %s: %s", video_id, exc)
        return None


@mcp.tool
def youtube_video_info(url: str) -> dict:
    """Look at a YouTube video without pulling its transcript.

    Returns title, channel, duration, the chapter list with deep links, the
    description, and which caption languages exist. Cheap and small.

    Call this first for a long video: read the chapters, then fetch only the
    part you need with `youtube_transcript(chapter=...)`. That is far cheaper
    than pulling a two-hour transcript to answer one question.
    """
    video_id = _resolve(url)
    info = _safe_info(video_id)
    if info is None:
        raise ToolError(f"Could not read video metadata for {video_id}.")

    long_form = bool(info.duration and info.duration >= 3600)
    description = info.description[:DESCRIPTION_LIMIT]

    return {
        "video_id": video_id,
        "url": f"https://youtu.be/{video_id}",
        "title": info.title,
        "channel": info.channel,
        "duration_seconds": info.duration,
        "duration_hms": timecode(info.duration, True) if info.duration else None,
        "upload_date": info.upload_date,
        "view_count": info.view_count,
        "description": description,
        "description_truncated": len(info.description) > DESCRIPTION_LIMIT,
        "chapter_count": len(info.chapters),
        "chapters": [
            {
                "index": c.index,
                "title": c.title,
                "start_seconds": c.start,
                "start": timecode(c.start, long_form),
                "url": deep_link(video_id, c.start),
            }
            for c in info.chapters
        ],
        "has_manual_captions": bool(info.manual_caption_languages),
        "caption_languages_available": len(
            info.manual_caption_languages or info.auto_caption_languages
        ),
    }


@mcp.tool
def youtube_transcript(
    url: str,
    format: str = "chapters",
    query: str | None = None,
    chapter: str | None = None,
    start: float | None = None,
    end: float | None = None,
    language: str = "en",
    max_chars: int = 40_000,
) -> dict:
    """Get the transcript of a YouTube video, merged into readable timestamped blocks.

    Accepts any YouTube URL shape (watch, youtu.be, shorts, embed, live) or a
    bare 11-character video id.

    Raw YouTube captions are ~7-word fragments; this merges them into paragraphs,
    groups them under the video's own chapters, and gives every block a
    timestamp and a deep link you can cite back to the user.

    For a long video, prefer a narrow read over the whole thing:
      - `chapter="5"` or `chapter="attention"` — one section, by number or title
      - `query="self-attention"` — only passages mentioning it, with context
      - `start=/end=` — an explicit time window in seconds

    Args:
        url: YouTube URL or video id.
        format: "chapters" (headed sections, best default), "timestamped"
            (flat [MM:SS] lines), or "plain" (prose, no timestamps).
        query: Return only blocks mentioning these words, plus surrounding context.
        chapter: Chapter number ("5") or a word from its title ("attention").
        start: Start of a time window, in seconds.
        end: End of a time window, in seconds.
        language: Preferred caption language code, e.g. "en", "it".
        max_chars: Response size cap. Lower it on mobile.
    """
    if format not in ("chapters", "timestamped", "plain"):
        raise ToolError(f"format must be 'chapters', 'timestamped' or 'plain', got {format!r}")

    max_chars = max(1_000, min(int(max_chars), MAX_CHARS_CEILING))
    video_id = _resolve(url)
    info = _safe_info(video_id)

    if chapter is not None:
        if info is None or not info.chapters:
            raise ToolError("This video has no chapters — use `query` or `start`/`end` instead.")
        found = find_chapter(info, chapter)
        if found is None:
            available = ", ".join(f"{c.index}. {c.title}" for c in info.chapters[:20])
            raise ToolError(f"No chapter matching {chapter!r}. Available: {available}")
        start, end = chapter_bounds(info, found)

    try:
        transcript = fetch_transcript(video_id, languages=[language])
    except TranscriptError as exc:
        raise ToolError(str(exc)) from exc

    return build_response(
        transcript,
        info,
        style=format,
        query=query,
        start=start,
        end=end,
        max_chars=max_chars,
    )


@mcp.tool
def health() -> dict:
    """Report server configuration and backend availability. No secrets returned."""
    import importlib.util

    return {
        "auth_provider": os.environ.get("YTM_AUTH_PROVIDER", "none"),
        "allowlist_size": len(_allowed_identities()),
        "proxy_configured": bool(os.environ.get("YTM_PROXY")),
        "whisper_fallback": bool(os.environ.get("GROQ_API_KEY")),
        "backends_importable": {
            name: importlib.util.find_spec(name) is not None
            for name in ("youtube_transcript_api", "yt_dlp")
        },
    }


def main() -> None:
    transport = os.environ.get("YTM_TRANSPORT", "stdio").strip().lower()
    if transport == "stdio":
        mcp.run()
        return

    mcp.run(
        transport="http",
        host=os.environ.get("YTM_HOST", "127.0.0.1"),
        port=int(os.environ.get("YTM_PORT", "8000")),
    )


if __name__ == "__main__":
    main()
