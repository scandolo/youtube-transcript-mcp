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


def webshare_credentials() -> tuple[str, str] | None:
    """Webshare "Proxy Username"/"Proxy Password", if both are configured."""
    username = os.environ.get("WEBSHARE_PROXY_USERNAME")
    password = os.environ.get("WEBSHARE_PROXY_PASSWORD")
    return (username, password) if username and password else None


def proxy() -> str | None:
    """Proxy URL for outbound YouTube requests.

    The `-rotate` suffix is the whole point of the Webshare branch: without it
    Webshare pins the session to one residential IP, which YouTube blocks about
    as readily as a datacenter one. With it, every request draws a fresh IP from
    the pool. An explicit YTM_PROXY still wins, for non-Webshare providers.
    """
    if explicit := os.environ.get("YTM_PROXY"):
        return explicit
    if credentials := webshare_credentials():
        username, password = credentials
        username = username.removesuffix("-rotate")
        return f"http://{username}-rotate:{password}@p.webshare.io:80/"
    return None
