"""Vercel entry point.

Vercel serves the ASGI `app` found in a root-level app.py. Stateless HTTP
because each request may land on a different instance, so no MCP session can
live in memory; OAuth state lives in Redis (REDIS_URL) for the same reason.
"""

from youtube_transcript_mcp.server import mcp

app = mcp.http_app(path="/mcp", stateless_http=True)
