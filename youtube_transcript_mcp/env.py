"""Environment-derived settings shared across modules."""

from __future__ import annotations

import os


def base_url() -> str | None:
    """Public URL of this server.

    Railway injects RAILWAY_PUBLIC_DOMAIN, so the OAuth base URL configures
    itself on that platform and only needs setting by hand elsewhere.
    """
    if explicit := os.environ.get("YTM_BASE_URL"):
        return explicit.rstrip("/")
    if domain := os.environ.get("RAILWAY_PUBLIC_DOMAIN"):
        return f"https://{domain}"
    return None


def api_referer() -> str | None:
    """Referer to send with YouTube Data API calls.

    A Google API key restricted to "Websites" checks this header. Servers send
    no Referer by default, so a key restricted that way rejects every
    server-side call until we set one explicitly. Derived from base_url() so
    the restriction keeps working without separate configuration.
    """
    root = base_url()
    return f"{root}/" if root else None


def proxy() -> str | None:
    return os.environ.get("YTM_PROXY") or None
