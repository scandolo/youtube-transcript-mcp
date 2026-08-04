"""Vercel entry point.

Vercel imports `app` from this module and serves it as an ASGI application.

Two Vercel-specific wrinkles are handled here:

1. The repo root goes on sys.path, because the package sits beside `api/`
   rather than being pip-installed into the function image.
2. A catch-all rewrite sends every request to `/api/index`, which means the
   ASGI app can receive that literal path instead of the one the client asked
   for. `_PathNormalizer` maps it back to `/mcp` so routing still works, and
   leaves the OAuth discovery paths untouched.

`/__debug` reports what the function actually received — the fastest way to
diagnose routing on a platform whose logs you may not be watching.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json  # noqa: E402

from youtube_transcript_mcp.server import mcp  # noqa: E402

_REWRITE_TARGET = "/api/index"
_MCP_PATH = "/mcp"


class _PathNormalizer:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        if path.rstrip("/") == "/__debug":
            body = json.dumps(
                {
                    "received_path": path,
                    "raw_path": (scope.get("raw_path") or b"").decode(errors="replace"),
                    "method": scope.get("method"),
                    "headers": {
                        k.decode(): v.decode()
                        for k, v in scope.get("headers", [])
                        if k.decode().startswith("x-vercel") or k.decode() == "host"
                    },
                    "mcp_path": _MCP_PATH,
                },
                indent=2,
            ).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        if path == _REWRITE_TARGET or path.startswith(_REWRITE_TARGET + "/"):
            remainder = path[len(_REWRITE_TARGET) :] or _MCP_PATH
            scope = dict(scope)
            scope["path"] = remainder
            scope["raw_path"] = remainder.encode()

        await self.app(scope, receive, send)


app = _PathNormalizer(mcp.http_app(path=_MCP_PATH))
