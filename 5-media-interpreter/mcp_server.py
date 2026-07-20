#!/usr/bin/env python3
"""MCP server exposing transcribe.py's capabilities as tools."""

import getpass
import logging
import os
import tempfile
import uuid
from functools import wraps
from pathlib import Path
from typing import Callable, TypeVar
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP

import transcribe as t

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("media-interpreter")

mcp = FastMCP("media-interpreter")

# Dedicated, app-owned workspace root. All MCP-tool file reads/writes are
# confined to this directory — never a shared system temp dir, never an
# arbitrary path supplied by the MCP client.
WORKSPACE_ROOT = Path.home() / ".media-interpreter" / "workspace"
WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)

ALLOWED_INSTAGRAM_HOSTS = {
    "instagram.com",
    "www.instagram.com",
    "vm.instagram.com",  # mobile share-sheet short links
    "instagr.am",        # legacy short domain
}


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
        # Report only the rejected input, never the resolved absolute path —
        # leaking it would help a client guess the real workspace location.
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


F = TypeVar("F", bound=Callable[..., str])


def _no_path_leak(fn: F) -> F:
    """Strip the real, resolved workspace absolute path out of any exception
    message before it reaches the MCP client. Underlying libraries (whisper,
    ffmpeg, open()) may embed the full resolved path in errors like
    FileNotFoundError; exposing that would hand a client the real on-disk
    workspace location, which the relative-path contract is meant to hide.

    Two additional redaction layers cover paths outside the workspace:
    - transcribe.interpret_video uses tempfile.TemporaryDirectory() for
      intermediate audio/frame extraction, which lives under the OS temp
      dir (e.g. C:\\Users\\<name>\\AppData\\Local\\Temp\\tmpXXXXXX on
      Windows) — outside WORKSPACE_ROOT, so it needs its own strip.
    - The OS username itself is redacted as defense in depth, since
      Windows can report either the long username or its DOS 8.3
      short-name alias (e.g. CRISTH~1) in subprocess-reported paths, and
      the short-name form is not reliably derivable from the long one.
      Enumerating every possible short-name alias is out of scope here;
      this is a documented residual limitation, not a full fix for that
      specific edge case.
    """
    workspace_str = str(WORKSPACE_ROOT.resolve())
    workspace_str_escaped = workspace_str.replace("\\", "\\\\")

    # Strip both the raw form tempfile.gettempdir() returns (which on
    # Windows may itself be a DOS 8.3 short-name path, e.g.
    # C:\Users\CRISTH~1\AppData\Local\Temp, if TEMP/TMP is set that way)
    # and its resolve()-normalized long-name form, since subprocess output
    # can embed either depending on how the OS reports it.
    tempdir_raw = tempfile.gettempdir()
    tempdir_resolved = str(Path(tempdir_raw).resolve())
    tempdir_strs = {tempdir_raw, tempdir_resolved}
    tempdir_strs |= {s.replace("\\", "\\\\") for s in tempdir_strs}

    try:
        os_username = os.getlogin()
    except OSError:
        try:
            os_username = getpass.getuser()
        except OSError:
            os_username = None

    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            # Log the original exception (with full traceback) server-side
            # before sanitizing it for the client, so operators can still
            # debug the real failure.
            logger.exception("media-interpreter tool failed: %s", fn.__name__)
            message = str(exc)
            message = message.replace(workspace_str, "<workspace>")
            if workspace_str_escaped != workspace_str:
                message = message.replace(workspace_str_escaped, "<workspace>")
            for s in tempdir_strs:
                message = message.replace(s, "<tempdir>")
            if os_username:
                # Case-insensitive substring replace; catches partial
                # appearances (e.g. within a short-name alias sharing a
                # prefix with the real username) as well as exact matches.
                lower_message = message.lower()
                lower_username = os_username.lower()
                if lower_username in lower_message:
                    idx = 0
                    result = []
                    while True:
                        pos = lower_message.find(lower_username, idx)
                        if pos == -1:
                            result.append(message[idx:])
                            break
                        result.append(message[idx:pos])
                        result.append("<user>")
                        idx = pos + len(lower_username)
                    message = "".join(result)
            # Never reconstruct the original exception type: many exceptions
            # (e.g. subprocess.CalledProcessError) require specific
            # constructor args beyond a single message string, and passing
            # just `message` would raise a TypeError that masks the real
            # error. A fixed exception type is sufficient since MCP clients
            # only ever see the stringified message anyway.
            raise RuntimeError(message) from None

    return wrapper  # type: ignore[return-value]


@mcp.tool()
@_no_path_leak
def transcribe_audio(audio_path: str, engine: str = "whisper",
                      model: str = "base", language: str | None = None) -> str:
    """Transcribe an audio file to text. engine: 'whisper' (local) or 'openai'.

    audio_path must be a relative path inside the media-interpreter workspace
    directory (see download_instagram_reel/extract_audio_from_video outputs).
    """
    safe_path = _resolve_in_workspace(audio_path)
    return t.transcribe_audio(safe_path, engine, model, language)


@mcp.tool()
@_no_path_leak
def extract_audio_from_video(video_path: str) -> str:
    """Extract audio track from a video file, return path to the resulting .wav.

    video_path must be a relative path inside the media-interpreter workspace directory.
    """
    safe_path = _resolve_in_workspace(video_path)
    out_path = safe_path.with_suffix(".wav")
    result = t.extract_audio_from_video(safe_path, out_path)
    return str(result.relative_to(WORKSPACE_ROOT.resolve()))


@mcp.tool()
@_no_path_leak
def interpret_video(video_path: str, prompt: str | None = None) -> str:
    """Process a whole video with an LLM: combined spoken transcript + visual description. Requires OPENAI_API_KEY.

    video_path must be a relative path inside the media-interpreter workspace directory.
    """
    safe_path = _resolve_in_workspace(video_path)
    return t.interpret_video(safe_path, prompt)


@mcp.tool()
@_no_path_leak
def download_instagram_reel(url: str) -> str:
    """Download an Instagram reel from a URL, return the local video file path
    (relative to the media-interpreter workspace directory)."""
    _validate_instagram_url(url)
    out_dir = WORKSPACE_ROOT / uuid.uuid4().hex
    result = t.download_instagram_reel(url, out_dir)
    return str(result.relative_to(WORKSPACE_ROOT.resolve()))


if __name__ == "__main__":
    mcp.run()
