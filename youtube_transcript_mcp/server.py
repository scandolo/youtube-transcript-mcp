"""The MCP server.

Three tools, deliberately shaped around how an agent actually works through a
video: find it (`search_youtube` — YouTube's own ranking, not the web's), orient
first (`youtube_video_info` — cheap, chapters and description), then drill in
(`youtube_transcript` — a chapter, a keyword search, or the lot).

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

from .env import base_url as _base_url
from .formatting import build_response, timecode
from .metadata import (
    QuotaExceeded,
    chapter_bounds,
    deep_link,
    fetch_video_info,
    find_chapter,
)
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


def _persist_oauth_state() -> None:
    """Anchor FastMCP's storage to disk that survives a deploy.

    FastMCP keeps registered OAuth clients under its home directory. On Railway
    the container filesystem is rebuilt on every deploy — and again whenever the
    app wakes from sleep — so that directory disappears, the connector's
    client_id stops being recognised, and the user is told to reauthorize after
    every ship. Pointing home at the mounted volume is what makes a session
    outlive a deploy; without a volume there is nowhere durable to put it, so
    say that plainly rather than failing mysteriously later.
    """
    if os.environ.get("FASTMCP_HOME"):
        return

    volume = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    if volume:
        home = os.path.join(volume, "fastmcp")
        os.makedirs(home, exist_ok=True)
        os.environ["FASTMCP_HOME"] = home
        log.info("OAuth state persisted to %s", home)
    elif os.environ.get("RAILWAY_SERVICE_ID"):
        log.warning(
            "No volume mounted: OAuth registrations live on an ephemeral disk and will be "
            "lost on the next deploy or sleep, forcing reauthorization. Mount a Railway "
            "volume (or set FASTMCP_HOME to durable storage) to stop that."
        )


def _build_auth():
    """Construct the OAuth provider named by YTM_AUTH_PROVIDER, or None."""
    provider = os.environ.get("YTM_AUTH_PROVIDER", "none").strip().lower()
    if provider in ("", "none"):
        return None

    base_url = _base_url()
    if not base_url:
        raise SystemExit(
            "Set YTM_BASE_URL to this server's public https URL when auth is enabled "
            "(on Railway this is derived from RAILWAY_PUBLIC_DOMAIN automatically)."
        )

    _persist_oauth_state()

    # Left unset, FastMCP derives the token key from the upstream client secret,
    # which ties every issued session to that secret: rotating it silently signs
    # everyone out. An explicit key decouples the two.
    signing_key = os.environ.get("JWT_SIGNING_KEY") or None

    if provider == "github":
        from fastmcp.server.auth.providers.github import GitHubProvider

        return GitHubProvider(
            client_id=os.environ["GITHUB_CLIENT_ID"],
            client_secret=os.environ["GITHUB_CLIENT_SECRET"],
            base_url=base_url,
            jwt_signing_key=signing_key,
        )

    if provider == "google":
        from fastmcp.server.auth.providers.google import GoogleProvider

        return GoogleProvider(
            client_id=os.environ["GOOGLE_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
            base_url=base_url,
            jwt_signing_key=signing_key,
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


def _safe_info(video_id: str) -> tuple[object | None, str | None]:
    """Metadata is a quality upgrade, not a dependency — degrade if it fails.

    Returns (info, warning). Degrading silently would leave an agent wondering
    why a chaptered video came back without chapters, so the reason travels
    with the response.
    """
    try:
        return fetch_video_info(video_id), None
    except QuotaExceeded as exc:
        log.warning("metadata quota exhausted for %s: %s", video_id, exc)
        return None, str(exc)
    except Exception as exc:
        log.warning("metadata lookup failed for %s: %s", video_id, exc)
        return None, (
            f"Video metadata unavailable ({type(exc).__name__}), so chapters, title and "
            "duration are missing from this response. The transcript itself is unaffected."
        )


@mcp.tool
def search_youtube(
    query: str,
    limit: int = 10,
    order: str = "relevance",
    duration: str = "any",
    published_after: str | None = None,
    channel_id: str | None = None,
) -> dict:
    """Search YouTube itself, ranked the way YouTube ranks it.

    This queries YouTube's own index, which is not the same as asking a web
    search engine for videos: the web index favours pages that are linked and
    written about, so it returns the famous ones, while YouTube ranks on watch
    behaviour, freshness and channel authority within its own catalogue. For
    "what would I find if I searched on YouTube", this is that.

    Every result carries a `url`, so pass one straight to `youtube_video_info`
    or `youtube_transcript` rather than rebuilding it.

    Args:
        query: What to search for.
        limit: How many results, 1-50. Default 10.
        order: relevance (default), date, viewCount, rating or title.
        duration: any (default), short (<4min), medium (4-20min), long (>20min).
        published_after: Only videos published on or after this YYYY-MM-DD date.
        channel_id: Restrict to one channel (a UC... id, not a handle).
    """
    from .search import search_videos

    try:
        results, source, warnings = search_videos(
            query,
            limit=limit,
            order=order,
            duration=duration,
            published_after=published_after,
            channel_id=channel_id,
        )
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    except QuotaExceeded as exc:
        raise ToolError(str(exc)) from exc
    except Exception as exc:
        raise ToolError(f"YouTube search failed: {exc}") from exc

    response = {
        "query": query,
        "result_count": len(results),
        "source": source,
        "results": [
            {
                "position": i,
                "video_id": r.video_id,
                "title": r.title,
                "channel": r.channel,
                "url": r.url,
                "published": r.published,
                "duration_seconds": r.duration,
                "duration_hms": timecode(r.duration, True) if r.duration else None,
                "view_count": r.view_count,
                "description": r.description[:300],
            }
            for i, r in enumerate(results, 1)
        ],
        # A short list can mean "that is all YouTube had" or "you asked for
        # fewer"; saying which stops the caller guessing.
        "limits": {
            "requested": limit,
            "returned": len(results),
            "max_supported": 50,
        },
    }
    if warnings:
        response["warnings"] = warnings
    return response


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
    info, warning = _safe_info(video_id)
    if info is None:
        raise ToolError(warning or f"Could not read video metadata for {video_id}.")

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
    info, warning = _safe_info(video_id)

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

    response = build_response(
        transcript,
        info,
        style=format,
        query=query,
        start=start,
        end=end,
        max_chars=max_chars,
    )

    # Say plainly what capped the output, so a short answer is never mistaken
    # for a complete one.
    response["limits"] = {
        "max_chars": max_chars,
        "truncated_by_max_chars": response["truncated"],
        "chapters_available": bool(info and info.chapters),
    }
    if warning:
        response["warnings"] = [warning]
    return response


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(request):
    """Plain HTTP healthcheck for the platform. Deliberately unauthenticated."""
    from starlette.responses import JSONResponse

    return JSONResponse(
        {
            "status": "ok",
            "auth_provider": os.environ.get("YTM_AUTH_PROVIDER", "none"),
            "base_url": _base_url(),
            "youtube_api_key_configured": bool(os.environ.get("YOUTUBE_API_KEY")),
            "github_client_id_configured": bool(os.environ.get("GITHUB_CLIENT_ID")),
        }
    )


@mcp.tool
def health() -> dict:
    """Report server configuration and backend availability. No secrets returned."""
    import importlib.util

    return {
        "auth_provider": os.environ.get("YTM_AUTH_PROVIDER", "none"),
        "allowlist_size": len(_allowed_identities()),
        "base_url": _base_url(),
        # Presence only — never the values. Enough to tell "variable never
        # reached this container" apart from "variable is wrong".
        "configured": {
            "YOUTUBE_API_KEY": bool(os.environ.get("YOUTUBE_API_KEY")),
            "GITHUB_CLIENT_ID": bool(os.environ.get("GITHUB_CLIENT_ID")),
            "GITHUB_CLIENT_SECRET": bool(os.environ.get("GITHUB_CLIENT_SECRET")),
            "JWT_SIGNING_KEY": bool(os.environ.get("JWT_SIGNING_KEY")),
            "YTM_PROXY": bool(os.environ.get("YTM_PROXY")),
            "WEBSHARE_PROXY_USERNAME": bool(os.environ.get("WEBSHARE_PROXY_USERNAME")),
            "WEBSHARE_PROXY_PASSWORD": bool(os.environ.get("WEBSHARE_PROXY_PASSWORD")),
            "GROQ_API_KEY": bool(os.environ.get("GROQ_API_KEY")),
            "RAILWAY_PUBLIC_DOMAIN": bool(os.environ.get("RAILWAY_PUBLIC_DOMAIN")),
        },
        "backends_importable": {
            name: importlib.util.find_spec(name) is not None
            for name in ("youtube_transcript_api", "yt_dlp")
        },
        # False means OAuth registrations sit on an ephemeral disk, so the next
        # deploy or sleep will force the connector to reauthorize.
        "oauth_state_persisted": bool(os.environ.get("FASTMCP_HOME")),
    }


def main() -> None:
    transport = os.environ.get("YTM_TRANSPORT", "stdio").strip().lower()
    if transport == "stdio":
        mcp.run()
        return

    # Railway (and most PaaS) assign the port at runtime via PORT.
    port = int(os.environ.get("PORT") or os.environ.get("YTM_PORT") or "8000")
    # Loopback is right locally and wrong on a platform that routes traffic into
    # the container — there it answers nothing and fails the healthcheck. An
    # injected PORT is the signal that we are behind such a router.
    host = os.environ.get("YTM_HOST") or ("0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
    log.info("serving MCP on http://%s:%s/mcp (base_url=%s)", host, port, _base_url())

    mcp.run(transport="http", host=host, port=port)


if __name__ == "__main__":
    main()
