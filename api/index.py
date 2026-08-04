"""Vercel entry point.

Vercel imports `app` from this module and serves it as an ASGI application.
The repo root is added to sys.path because the package lives beside `api/`
rather than being pip-installed into the function image.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from youtube_transcript_mcp.server import mcp  # noqa: E402

app = mcp.http_app(path="/mcp")
