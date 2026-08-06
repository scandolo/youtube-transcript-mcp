"""Search YouTube the way YouTube ranks it.

A web search that happens to surface videos and a search performed *on YouTube*
return noticeably different things: the web index favours pages that are linked
and written about, while YouTube ranks on watch behaviour, freshness and channel
authority within its own catalogue. Asking the former for videos gives you the
famous ones; asking the latter gives you what a viewer would actually find.

Both backends here query YouTube's own index, so the ordering is YouTube's:

1. Data API ``search.list`` — key-authenticated, so it works from datacenter IPs
   where scraping does not. Costs 100 quota units per call against a 10,000/day
   free allowance, which is the real constraint: ~100 searches a day.
2. ``yt-dlp`` — reads the results page itself. No quota at all, so it carries on
   once the API allowance is gone, but it needs the residential proxy and is
   slower.

Results carry a ``url`` so a caller can feed one straight into
``youtube_video_info`` or ``youtube_transcript`` without reassembling anything.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import httpx

from .env import api_referer, proxy
from .metadata import QuotaExceeded, _classify_403, _iso_duration_seconds

log = logging.getLogger(__name__)

_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"

#: search.list caps at 50 per call, and a long result list is rarely what an
#: agent wants to read anyway.
MAX_RESULTS = 50

ORDERS = ("relevance", "date", "viewCount", "rating", "title")
DURATIONS = ("any", "short", "medium", "long")


@dataclass
class SearchResult:
    video_id: str
    title: str
    channel: str | None = None
    description: str = ""
    published: str | None = None
    duration: float | None = None
    view_count: int | None = None

    @property
    def url(self) -> str:
        return f"https://youtu.be/{self.video_id}"


def _clamp(limit: int) -> int:
    return max(1, min(int(limit), MAX_RESULTS))


# --------------------------------------------------------------------------
# Backend 1 — Data API search.list
# --------------------------------------------------------------------------


def _enrich_durations(results: list[SearchResult], key: str, headers: dict) -> None:
    """Add duration and view count, which search.list does not return.

    Worth the extra call: duration is usually what decides between two
    otherwise-similar hits, and a videos.list for up to 50 ids costs 1 unit
    against the 100 the search itself just cost. Failure here is not fatal —
    the results are still usable without it.
    """
    if not results:
        return

    kwargs = {"timeout": 20}
    if p := proxy():
        kwargs["proxy"] = p

    try:
        with httpx.Client(**kwargs) as client:
            response = client.get(
                _VIDEOS_URL,
                params={
                    "part": "contentDetails,statistics",
                    "id": ",".join(r.video_id for r in results),
                    "key": key,
                },
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        log.debug("duration enrichment failed: %s", exc)
        return

    by_id = {item.get("id"): item for item in payload.get("items") or []}
    for result in results:
        item = by_id.get(result.video_id)
        if not item:
            continue
        result.duration = _iso_duration_seconds((item.get("contentDetails") or {}).get("duration", ""))
        if views := (item.get("statistics") or {}).get("viewCount"):
            result.view_count = int(views)


def _via_data_api(
    query: str,
    limit: int,
    order: str,
    duration: str,
    published_after: str | None,
    channel_id: str | None,
) -> list[SearchResult] | None:
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        return None

    headers = {}
    if referer := api_referer():
        headers["Referer"] = referer

    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": limit,
        "order": order,
        "key": key,
    }
    if duration != "any":
        params["videoDuration"] = duration
    if published_after:
        # The API wants RFC 3339; a plain date is the friendlier input.
        params["publishedAfter"] = f"{published_after}T00:00:00Z"
    if channel_id:
        params["channelId"] = channel_id

    kwargs = {"timeout": 20}
    if p := proxy():
        kwargs["proxy"] = p

    with httpx.Client(**kwargs) as client:
        response = client.get(_SEARCH_URL, params=params, headers=headers)
        if response.status_code == 403:
            raise _classify_403(response)
        response.raise_for_status()
        payload = response.json()

    results = []
    for item in payload.get("items") or []:
        video_id = (item.get("id") or {}).get("videoId")
        if not video_id:
            continue
        snippet = item.get("snippet") or {}
        results.append(
            SearchResult(
                video_id=video_id,
                title=snippet.get("title") or "Untitled",
                channel=snippet.get("channelTitle"),
                description=snippet.get("description") or "",
                published=(snippet.get("publishedAt") or "")[:10] or None,
            )
        )

    if not results:
        return None

    _enrich_durations(results, key, headers)
    return results


# --------------------------------------------------------------------------
# Backend 2 — yt-dlp against the results page
# --------------------------------------------------------------------------


def _via_yt_dlp(query: str, limit: int, order: str, **_ignored) -> list[SearchResult] | None:
    """Read the search results page directly.

    Only the query and the count survive here — the filters are Data API
    features, and the caller is told which ones were dropped rather than being
    handed a silently unfiltered list.
    """
    import yt_dlp

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        # Flat extraction lists results without resolving each video, which is
        # the difference between one request and `limit` of them.
        "extract_flat": True,
    }
    if p := proxy():
        opts["proxy"] = p

    prefix = "ytsearchdate" if order == "date" else "ytsearch"
    with yt_dlp.YoutubeDL(opts) as ydl:
        payload = ydl.extract_info(f"{prefix}{limit}:{query}", download=False)

    results = []
    for entry in (payload or {}).get("entries") or []:
        video_id = entry.get("id")
        if not video_id:
            continue
        results.append(
            SearchResult(
                video_id=video_id,
                title=entry.get("title") or "Untitled",
                channel=entry.get("channel") or entry.get("uploader"),
                description=entry.get("description") or "",
                duration=entry.get("duration"),
                view_count=entry.get("view_count"),
            )
        )

    return results or None


# --------------------------------------------------------------------------


def search_videos(
    query: str,
    *,
    limit: int = 10,
    order: str = "relevance",
    duration: str = "any",
    published_after: str | None = None,
    channel_id: str | None = None,
) -> tuple[list[SearchResult], str, list[str]]:
    """Search YouTube. Returns (results, source, warnings).

    The Data API goes first because it is key-authenticated and supports the
    filters; yt-dlp takes over when the key is missing or its daily allowance is
    spent, which is exactly when a hard failure would be most annoying.
    """
    query = (query or "").strip()
    if not query:
        raise ValueError("Search query is empty.")

    if order not in ORDERS:
        raise ValueError(f"order must be one of {', '.join(ORDERS)} (got {order!r})")
    if duration not in DURATIONS:
        raise ValueError(f"duration must be one of {', '.join(DURATIONS)} (got {duration!r})")

    limit = _clamp(limit)
    warnings: list[str] = []
    quota: QuotaExceeded | None = None

    backends = (("data-api", _via_data_api), ("yt-dlp", _via_yt_dlp))
    for name, backend in backends:
        try:
            results = backend(
                query,
                limit,
                order,
                duration=duration,
                published_after=published_after,
                channel_id=channel_id,
            )
        except QuotaExceeded as exc:
            quota = exc
            warnings.append(str(exc))
            log.warning("search backend %s out of quota: %s", name, exc)
            continue
        except Exception as exc:
            warnings.append(f"{name}: {type(exc).__name__}: {exc}")
            log.warning("search backend %s failed for %r: %s", name, query, exc)
            continue

        if results:
            if name == "yt-dlp":
                dropped = [
                    label
                    for label, active in (
                        ("duration", duration != "any"),
                        ("published_after", bool(published_after)),
                        ("channel_id", bool(channel_id)),
                        ("order", order not in ("relevance", "date")),
                    )
                    if active
                ]
                if dropped:
                    warnings.append(
                        "Served without the YouTube Data API, which is what applies filters: "
                        f"{', '.join(dropped)} {'was' if len(dropped) == 1 else 'were'} ignored."
                    )
            return results, name, warnings

    if quota is not None:
        raise quota
    raise RuntimeError(f"No search backend returned results for {query!r}. " + "; ".join(warnings))
