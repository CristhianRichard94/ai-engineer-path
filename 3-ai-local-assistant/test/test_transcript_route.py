"""
test/test_transcript_route.py — Coverage for ui/server.py's
_read_transcript() helper and GET /transcript route, focused on
conversation_id scoping.

Verifies that:
  - _read_transcript(conversation_id=...) filters entries to a single
    conversation before applying the entry-count limit (so a long
    conversation isn't starved by unrelated lines from other
    conversations).
  - _read_transcript(limit=None) returns everything, unfiltered by count.
  - _read_transcript() with conversation_id=None keeps today's exact
    unfiltered last-N behavior.
  - GET /transcript defaults to the current shared brain's
    conversation_id when no query param is given, and honors an explicit
    ?conversation_id= query param override.
"""

import json
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
JARVIS_DIR = os.path.join(ROOT, "jarvis")
if JARVIS_DIR not in sys.path:
    sys.path.insert(0, JARVIS_DIR)
UI_DIR = os.path.join(ROOT, "ui")
if UI_DIR not in sys.path:
    sys.path.insert(0, UI_DIR)

from unittest.mock import MagicMock  # noqa: E402
for mod in ("pycaw", "pycaw.pycaw", "comtypes", "spotipy",
            "spotipy.oauth2", "spotipy.exceptions", "anthropic", "openai"):
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

import server as server_module  # noqa: E402


def _line(role, text, ts, conversation_id=None):
    entry = {"role": role, "text": text, "ts": ts}
    if conversation_id is not None:
        entry["conversation_id"] = conversation_id
    return json.dumps(entry)


class TestReadTranscript(unittest.TestCase):

    def setUp(self):
        self._orig_transcript = server_module.TRANSCRIPT_FILE
        fd, self._tmp_transcript = __import__("tempfile").mkstemp(suffix=".jsonl")
        os.close(fd)
        server_module.TRANSCRIPT_FILE = self._tmp_transcript

        self._orig_brain = server_module._brain
        server_module._brain = None

    def tearDown(self):
        server_module.TRANSCRIPT_FILE = self._orig_transcript
        server_module._brain = self._orig_brain
        if os.path.exists(self._tmp_transcript):
            os.remove(self._tmp_transcript)

    def _write_lines(self, lines):
        with open(self._tmp_transcript, "w", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")

    def test_no_conversation_id_keeps_unfiltered_last_n_behavior(self):
        self._write_lines([
            _line("user", "a", 1, conversation_id="conv-1"),
            _line("assistant", "b", 2, conversation_id="conv-2"),
            _line("user", "c", 3, conversation_id="conv-1"),
        ])

        entries = server_module._read_transcript(limit=2)
        self.assertEqual([e["text"] for e in entries], ["b", "c"])

    def test_conversation_id_filters_before_limit_is_applied(self):
        # 5 lines from conv-2 interleaved between conv-1 lines - a limit
        # of 2 applied globally-then-filtered would starve conv-1 to
        # nothing, but filtering first must still surface conv-1's last
        # two lines.
        lines = [_line("user", "conv1-first", 1, conversation_id="conv-1")]
        for i in range(5):
            lines.append(_line("user", "noise-{}".format(i), 10 + i, conversation_id="conv-2"))
        lines.append(_line("assistant", "conv1-last", 100, conversation_id="conv-1"))
        self._write_lines(lines)

        entries = server_module._read_transcript(limit=2, conversation_id="conv-1")
        self.assertEqual([e["text"] for e in entries], ["conv1-first", "conv1-last"])

    def test_limit_none_returns_everything(self):
        lines = [_line("user", "line-{}".format(i), i, conversation_id="conv-1") for i in range(10)]
        self._write_lines(lines)

        entries = server_module._read_transcript(limit=None)
        self.assertEqual(len(entries), 10)

    def test_missing_file_returns_empty_list(self):
        os.remove(self._tmp_transcript)
        self.assertEqual(server_module._read_transcript(conversation_id="conv-1"), [])

    def test_conversation_id_with_no_matches_returns_empty(self):
        self._write_lines([_line("user", "a", 1, conversation_id="conv-1")])
        self.assertEqual(server_module._read_transcript(conversation_id="conv-999"), [])


class TestTranscriptRoute(unittest.TestCase):

    def setUp(self):
        self._orig_transcript = server_module.TRANSCRIPT_FILE
        fd, self._tmp_transcript = __import__("tempfile").mkstemp(suffix=".jsonl")
        os.close(fd)
        server_module.TRANSCRIPT_FILE = self._tmp_transcript
        with open(self._tmp_transcript, "w", encoding="utf-8") as f:
            f.write(_line("user", "hi-1", 1, conversation_id="conv-1") + "\n")
            f.write(_line("user", "hi-2", 2, conversation_id="conv-2") + "\n")

        self._orig_brain = server_module._brain
        server_module._brain = None

        self.client = server_module.app.test_client()

    def tearDown(self):
        server_module.TRANSCRIPT_FILE = self._orig_transcript
        server_module._brain = self._orig_brain
        if os.path.exists(self._tmp_transcript):
            os.remove(self._tmp_transcript)

    def test_no_query_param_and_no_brain_returns_unfiltered(self):
        resp = self.client.get("/transcript")
        self.assertEqual(resp.status_code, 200)
        texts = [e["text"] for e in resp.get_json()]
        self.assertEqual(texts, ["hi-1", "hi-2"])

    def test_no_query_param_defaults_to_current_brain_conversation_id(self):
        mock_brain = mock.MagicMock()
        mock_brain.conversation_id = "conv-1"
        server_module._brain = mock_brain

        resp = self.client.get("/transcript")
        self.assertEqual(resp.status_code, 200)
        texts = [e["text"] for e in resp.get_json()]
        self.assertEqual(texts, ["hi-1"])

    def test_explicit_query_param_overrides_current_brain(self):
        mock_brain = mock.MagicMock()
        mock_brain.conversation_id = "conv-1"
        server_module._brain = mock_brain

        resp = self.client.get("/transcript?conversation_id=conv-2")
        self.assertEqual(resp.status_code, 200)
        texts = [e["text"] for e in resp.get_json()]
        self.assertEqual(texts, ["hi-2"])


if __name__ == "__main__":
    unittest.main()
