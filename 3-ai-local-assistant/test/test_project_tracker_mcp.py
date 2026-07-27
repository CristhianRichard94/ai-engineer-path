"""
test/test_project_tracker_mcp.py — Unit tests for the direct stdio MCP
client to the project-tracker MCP server.

No real Node subprocess is spawned in tests: `mcp.client.stdio.stdio_client`
and `mcp.ClientSession` are mocked at the module level.
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
JARVIS_DIR = os.path.join(ROOT, "jarvis")
if JARVIS_DIR not in sys.path:
    sys.path.insert(0, JARVIS_DIR)

import project_tracker_mcp as ptm


def _make_call_tool_result(text="hello", is_error=False):
    block = MagicMock()
    block.text = text
    result = MagicMock()
    result.content = [block]
    result.isError = is_error
    return result


class _FakeAsyncCM:
    """A minimal async context manager wrapping a fixed return value."""

    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *exc_info):
        return False


class TestCallTool(unittest.TestCase):

    @patch("project_tracker_mcp.shutil.which", return_value="C:\\fake\\node.exe")
    @patch("project_tracker_mcp.ClientSession")
    @patch("project_tracker_mcp.stdio_client")
    def test_successful_call_returns_text(self, mock_stdio_client, mock_session_cls, mock_which):
        mock_read, mock_write = object(), object()
        mock_stdio_client.return_value = _FakeAsyncCM((mock_read, mock_write))

        mock_session = MagicMock()
        mock_session.initialize = AsyncMock()
        mock_session.call_tool = AsyncMock(
            return_value=_make_call_tool_result("No open tasks.")
        )
        mock_session_cls.return_value = _FakeAsyncCM(mock_session)

        result = ptm.call_tool("list_open_tasks")

        self.assertEqual(result, "No open tasks.")
        mock_session.initialize.assert_awaited_once()
        mock_session.call_tool.assert_awaited_once_with("list_open_tasks", {})

    @patch("project_tracker_mcp.shutil.which", return_value="C:\\fake\\node.exe")
    @patch("project_tracker_mcp.ClientSession")
    @patch("project_tracker_mcp.stdio_client")
    def test_tool_level_error_raises(self, mock_stdio_client, mock_session_cls, mock_which):
        mock_stdio_client.return_value = _FakeAsyncCM((object(), object()))

        mock_session = MagicMock()
        mock_session.initialize = AsyncMock()
        mock_session.call_tool = AsyncMock(
            return_value=_make_call_tool_result("Error: sheet unreachable", is_error=True)
        )
        mock_session_cls.return_value = _FakeAsyncCM(mock_session)

        with self.assertRaises(ptm.ProjectTrackerMCPError) as ctx:
            ptm.call_tool("list_open_tasks")
        self.assertIn("sheet unreachable", str(ctx.exception))

    @patch("project_tracker_mcp.shutil.which", return_value="C:\\fake\\node.exe")
    @patch("project_tracker_mcp.ClientSession")
    @patch("project_tracker_mcp.stdio_client")
    def test_timeout_raises(self, mock_stdio_client, mock_session_cls, mock_which):
        async def _never_initializes():
            await asyncio.sleep(9999)

        mock_session = MagicMock()
        mock_session.initialize = MagicMock(side_effect=lambda: _never_initializes())
        mock_session_cls.return_value = _FakeAsyncCM(mock_session)
        mock_stdio_client.return_value = _FakeAsyncCM((object(), object()))

        with patch.object(ptm, "_CALL_TIMEOUT_SECONDS", 0.05):
            with self.assertRaises(ptm.ProjectTrackerMCPError) as ctx:
                ptm.call_tool("list_open_tasks")
        self.assertIn("Timed out", str(ctx.exception))

    @patch("project_tracker_mcp.shutil.which", return_value=None)
    def test_missing_node_binary_raises(self, mock_which):
        with self.assertRaises(ptm.ProjectTrackerMCPError) as ctx:
            ptm.call_tool("list_open_tasks")
        self.assertIn("Node.js", str(ctx.exception))

    @patch("project_tracker_mcp.shutil.which", return_value="C:\\fake\\node.exe")
    @patch("project_tracker_mcp.stdio_client", side_effect=OSError("spawn failed"))
    def test_server_spawn_failure_raises(self, mock_stdio_client, mock_which):
        with self.assertRaises(ptm.ProjectTrackerMCPError) as ctx:
            ptm.call_tool("list_open_tasks")
        self.assertIn("Failed to reach", str(ctx.exception))

    @patch("project_tracker_mcp.shutil.which", return_value="C:\\fake\\node.exe")
    @patch("project_tracker_mcp.os.path.isfile", return_value=False)
    def test_missing_server_script_raises(self, mock_isfile, mock_which):
        with self.assertRaises(ptm.ProjectTrackerMCPError) as ctx:
            ptm.call_tool("list_open_tasks")
        self.assertIn("not found", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
