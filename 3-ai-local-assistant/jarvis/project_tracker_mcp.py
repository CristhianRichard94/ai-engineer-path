"""
project_tracker_mcp.py - Direct stdio MCP client for the project-tracker MCP
server (4-project-tracker/mcp-server/src/index.js), bypassing the Claude Code
CLI for this one skill.

JARVIS's codebase is otherwise all sync/blocking (requests.get,
subprocess.run, etc.), so this module wraps the async MCP SDK client behind a
single sync entry point, `call_tool()`, using `asyncio.run()` at the call
boundary. No persistent connection is kept across calls: each call spawns a
fresh `node` subprocess running the MCP server, does the initialize
handshake, calls the tool, and tears the session down. This is a low
frequency, latency-tolerant voice-assistant call path (not a hot loop), so
the simplicity of "spawn fresh every time" is worth more than the effort of
managing a long-lived session's error recovery.
"""

import asyncio
import os
import shutil

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)
_MCP_SERVER_SCRIPT = os.path.join(
    _REPO_ROOT, "4-project-tracker", "mcp-server", "src", "index.js"
)

_CALL_TIMEOUT_SECONDS = 15


class ProjectTrackerMCPError(Exception):
    """Raised when the project-tracker MCP tool call fails for any reason
    (missing node binary, server crash, timeout, tool-level error)."""


async def _call_tool_async(tool_name: str, arguments: dict) -> str:
    node_path = shutil.which("node")
    if not node_path:
        raise ProjectTrackerMCPError(
            "Node.js ('node') is not on PATH; cannot start the "
            "project-tracker MCP server."
        )

    if not os.path.isfile(_MCP_SERVER_SCRIPT):
        raise ProjectTrackerMCPError(
            "project-tracker MCP server script not found at {}".format(
                _MCP_SERVER_SCRIPT
            )
        )

    server_params = StdioServerParameters(
        command=node_path,
        args=[_MCP_SERVER_SCRIPT],
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
    except Exception as e:
        raise ProjectTrackerMCPError(
            "Failed to reach the project-tracker MCP server: {}".format(e)
        ) from e

    if getattr(result, "isError", False):
        error_text = _extract_text(result)
        raise ProjectTrackerMCPError(
            "project-tracker MCP tool '{}' returned an error: {}".format(
                tool_name, error_text or "(no details)"
            )
        )

    return _extract_text(result)


def _extract_text(result) -> str:
    """Concatenate all text-typed content blocks from a CallToolResult."""
    parts = []
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def call_tool(tool_name: str, arguments: dict = None) -> str:
    """Synchronously call a tool on the project-tracker MCP server.

    Spawns a fresh `node src/index.js` subprocess, performs the MCP
    initialize handshake, calls `tool_name` with `arguments`, and tears the
    connection down. Returns the tool's concatenated text content.

    Raises ProjectTrackerMCPError on any failure: missing `node` binary,
    missing server script, server crash/connection failure, tool-level
    error result, or timeout (~15s).
    """
    try:
        return asyncio.run(
            asyncio.wait_for(
                _call_tool_async(tool_name, arguments or {}),
                timeout=_CALL_TIMEOUT_SECONDS,
            )
        )
    except asyncio.TimeoutError as e:
        raise ProjectTrackerMCPError(
            "Timed out after {}s waiting for the project-tracker MCP "
            "server (tool: {}).".format(_CALL_TIMEOUT_SECONDS, tool_name)
        ) from e
