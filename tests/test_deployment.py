"""Startup checks for the settings that make a Railway clone usable."""

import os
import subprocess
import sys

from starlette.testclient import TestClient

from youtube_transcript_mcp.server import (
    _missing_railway_settings,
    _persist_oauth_state,
    _setup_app,
)


def _clean_env() -> dict[str, str]:
    prefixes = ("YTM_", "RAILWAY_", "GITHUB_CLIENT_", "GOOGLE_CLIENT_", "FASTMCP_")
    return {k: v for k, v in os.environ.items() if not k.startswith(prefixes)}


def _start(extra: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = _clean_env()
    env.update(extra)
    return subprocess.run(
        [sys.executable, "-c", "import youtube_transcript_mcp.server"],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )


def test_railway_setup_status(monkeypatch):
    for key in ("YTM_PROXY", "WEBSHARE_PROXY_USERNAME", "WEBSHARE_PROXY_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("RAILWAY_SERVICE_ID", "test")
    missing = _missing_railway_settings()
    assert any("residential proxy" in item for item in missing)

    with TestClient(_setup_app(missing)) as client:
        assert client.get("/healthz").json() == {"status": "setup_required", "missing": missing}
        assert client.get("/mcp").status_code == 503
        assert client.post("/mcp").status_code == 503
        assert client.get("/tools").status_code == 404


def test_railway_defaults_to_github_auth():
    result = _start({"RAILWAY_SERVICE_ID": "test", "YTM_PROXY": "http://proxy.example:80"})
    assert result.returncode == 0
    assert "Railway setup incomplete" in result.stderr
    assert "GITHUB_CLIENT_ID" in result.stderr
    assert "YTM_AUTH_PROVIDER" not in result.stderr


def test_railway_requires_oauth_credentials():
    result = _start(
        {
            "RAILWAY_SERVICE_ID": "test",
            "RAILWAY_PUBLIC_DOMAIN": "example.up.railway.app",
            "YTM_PROXY": "http://proxy.example:80",
            "YTM_AUTH_PROVIDER": "github",
        }
    )
    assert result.returncode == 0
    assert "GITHUB_CLIENT_ID" in result.stderr
    assert "GITHUB_CLIENT_SECRET" in result.stderr


def test_railway_volume_is_used_by_fastmcp(tmp_path):
    env = _clean_env()
    env.update(
        {
            "RAILWAY_SERVICE_ID": "test",
            "RAILWAY_PUBLIC_DOMAIN": "example.up.railway.app",
            "RAILWAY_VOLUME_MOUNT_PATH": str(tmp_path),
            "YTM_PROXY": "http://proxy.example:80",
            "YTM_AUTH_PROVIDER": "github",
            "YTM_ALLOWED_USERS": "testuser",
            "GITHUB_CLIENT_ID": "test-id",
            "GITHUB_CLIENT_SECRET": "test-secret",
            "JWT_SIGNING_KEY": "a" * 64,
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import fastmcp; import youtube_transcript_mcp.server; print(fastmcp.settings.home)",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(tmp_path / "fastmcp")
    assert list((tmp_path / "fastmcp" / "oauth-proxy").iterdir())


def test_explicit_fastmcp_home_after_import(monkeypatch, tmp_path):
    from fastmcp import settings

    monkeypatch.setattr(settings, "home", tmp_path / "old")
    monkeypatch.setenv("FASTMCP_HOME", str(tmp_path / "new"))
    _persist_oauth_state()
    assert settings.home == tmp_path / "new"
