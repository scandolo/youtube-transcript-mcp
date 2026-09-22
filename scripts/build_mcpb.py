"""Build a small, cross-platform Claude Desktop extension with uv-managed Python."""

from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "packaging/mcpb/manifest.json"


def main() -> None:
    manifest = json.loads(MANIFEST.read_text())
    if manifest["version"] != _project_version():
        raise SystemExit("MCPB version must match pyproject.toml")

    output = ROOT / "dist" / f"youtube-transcript-mcp-{manifest['version']}.mcpb"
    output.parent.mkdir(exist_ok=True)
    files = {
        "manifest.json": MANIFEST,
        "server/main.py": ROOT / "packaging/mcpb/server/main.py",
        "pyproject.toml": ROOT / "pyproject.toml",
        "README.md": ROOT / "README.md",
        "LICENSE": ROOT / "LICENSE",
        "assets/icon.png": ROOT / "assets/icon.png",
    }
    files.update(
        (f"youtube_transcript_mcp/{path.name}", path)
        for path in (ROOT / "youtube_transcript_mcp").glob("*.py")
    )
    with ZipFile(output, "w", ZIP_DEFLATED) as bundle:
        for name, source in sorted(files.items()):
            bundle.write(source, name)
    print(output)


def _project_version() -> str:
    import re

    project = (ROOT / "pyproject.toml").read_text().split("[project]", 1)[1].split("[", 1)[0]
    match = re.search(r'^version\s*=\s*"([^"]+)"', project, re.MULTILINE)
    if not match:
        raise SystemExit("Missing project version in pyproject.toml")
    return match.group(1)


if __name__ == "__main__":
    main()
