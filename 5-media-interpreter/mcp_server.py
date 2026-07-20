#!/usr/bin/env python3
"""MCP server exposing transcribe.py's capabilities as tools."""

import uuid
from pathlib import Path
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP

import transcribe as t

mcp = FastMCP("media-interpreter")

# Dedicated, app-owned workspace root. All MCP-tool file reads/writes are
# confined to this directory — never a shared system temp dir, never an
# arbitrary path supplied by the MCP client.
WORKSPACE_ROOT = Path.home() / ".media-interpreter" / "workspace"
WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)

ALLOWED_INSTAGRAM_HOSTS = {"instagram.com", "www.instagram.com"}


def _resolve_in_workspace(path_str: str, workspace_root: Path = WORKSPACE_ROOT) -> Path:
    """Resolve an MCP-supplied path string to a file confined to workspace_root.

    Rejects:
    - any string containing a URI scheme marker ("://"), e.g. remote URLs
    - absolute paths
    - paths that resolve outside workspace_root (e.g. via "..")
    """
    if "://" in path_str:
        raise ValueError(f"Path must not contain a URI scheme: {path_str!r}")

    candidate = Path(path_str)
    if candidate.is_absolute():
        raise ValueError(f"Absolute paths are not allowed: {path_str!r}")

    workspace_root = workspace_root.resolve()
    resolved = (workspace_root / candidate).resolve()

    if not (resolved == workspace_root or resolved.is_relative_to(workspace_root)):
        raise ValueError(f"Path escapes the workspace: {path_str!r}")

    return resolved


def _validate_instagram_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL must use http/https: {url!r}")
    netloc = parsed.netloc.lower()
    # strip credentials/port if present, e.g. user:pass@host:443
    host = netloc.split("@")[-1].split(":")[0]
    if host not in ALLOWED_INSTAGRAM_HOSTS:
        raise ValueError(f"URL host is not an allowed Instagram host: {host!r}")


@mcp.tool()
def transcribe_audio(audio_path: str, engine: str = "whisper",
                      model: str = "base", language: str | None = None) -> str:
    """Transcribe an audio file to text. engine: 'whisper' (local) or 'openai'.

    audio_path must be a relative path inside the media-interpreter workspace
    directory (see download_instagram_reel/extract_audio_from_video outputs).
    """
    safe_path = _resolve_in_workspace(audio_path)
    return t.transcribe_audio(safe_path, engine, model, language)


@mcp.tool()
def extract_audio_from_video(video_path: str) -> str:
    """Extract audio track from a video file, return path to the resulting .wav.

    video_path must be a relative path inside the media-interpreter workspace directory.
    """
    safe_path = _resolve_in_workspace(video_path)
    out_path = safe_path.with_suffix(".wav")
    result = t.extract_audio_from_video(safe_path, out_path)
    return str(result.relative_to(WORKSPACE_ROOT.resolve()))


@mcp.tool()
def interpret_video(video_path: str, prompt: str | None = None) -> str:
    """Process a whole video with an LLM: combined spoken transcript + visual description. Requires OPENAI_API_KEY.

    video_path must be a relative path inside the media-interpreter workspace directory.
    """
    safe_path = _resolve_in_workspace(video_path)
    return t.interpret_video(safe_path, prompt)


@mcp.tool()
def download_instagram_reel(url: str) -> str:
    """Download an Instagram reel from a URL, return the local video file path
    (relative to the media-interpreter workspace directory)."""
    _validate_instagram_url(url)
    out_dir = WORKSPACE_ROOT / uuid.uuid4().hex
    result = t.download_instagram_reel(url, out_dir)
    return str(result.relative_to(WORKSPACE_ROOT.resolve()))


if __name__ == "__main__":
    mcp.run()
