"""
test/test_conversations_route.py — Flask test-client coverage for
ui/server.py's GET /conversations route.

Verifies conversations are grouped from transcript.jsonl by
conversation_id, ordered chronologically by first appearance, with
accurate turn_count, a preview taken from the first user-role text
(truncated to 80 chars), untagged lines skipped without creating bogus
groups, and an empty transcript file yielding [].
"""

import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
JARVIS_DIR = os.path.join(ROOT, "jarvis")
if JARVIS_DIR not in sys.path:
    sys.path.insert(0, JARVIS_DIR)
UI_DIR = os.path.join(ROOT, "ui")
if UI_DIR not in sys.path:
    sys.path.insert(0, UI_DIR)

# `anthropic`/`openai` are only stubbed if genuinely unavailable —
# unconditionally overwriting sys.modules here would clobber the real
# package for other test modules (e.g. test_claude_client.py) that need
# real anthropic exception types to construct.
import importlib  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402
for mod in ("pycaw", "pycaw.pycaw", "comtypes", "spotipy",
            "spotipy.oauth2", "spotipy.exceptions", "anthropic", "openai"):
    if mod in sys.modules:
        continue
    try:
        importlib.import_module(mod)
    except ImportError:
        sys.modules[mod] = MagicMock()

import server as server_module  # noqa: E402


def _line(role, text, ts, conversation_id=None):
    entry = {"role": role, "text": text, "ts": ts}
    if conversation_id is not None:
        entry["conversation_id"] = conversation_id
    return json.dumps(entry)


class TestConversationsRoute(unittest.TestCase):

    def setUp(self):
        self._orig_transcript = server_module.TRANSCRIPT_FILE
        fd, self._tmp_transcript = __import__("tempfile").mkstemp(suffix=".jsonl")
        os.close(fd)
        server_module.TRANSCRIPT_FILE = self._tmp_transcript

        self.client = server_module.app.test_client()

    def tearDown(self):
        server_module.TRANSCRIPT_FILE = self._orig_transcript
        if os.path.exists(self._tmp_transcript):
            os.remove(self._tmp_transcript)

    def _write_lines(self, lines):
        with open(self._tmp_transcript, "w", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")

    def test_empty_transcript_returns_empty_list(self):
        self._write_lines([])
        resp = self.client.get("/conversations")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), [])

    def test_missing_transcript_file_returns_empty_list(self):
        os.remove(self._tmp_transcript)
        resp = self.client.get("/conversations")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), [])

    def test_groups_by_conversation_id_in_chronological_first_appearance_order(self):
        self._write_lines([
            _line("user", "hi from conv-b", 1, conversation_id="conv-b"),
            _line("user", "hi from conv-a", 2, conversation_id="conv-a"),
            _line("assistant", "reply for b", 3, conversation_id="conv-b"),
        ])

        resp = self.client.get("/conversations")
        self.assertEqual(resp.status_code, 200)
        cids = [g["conversation_id"] for g in resp.get_json()]
        self.assertEqual(cids, ["conv-b", "conv-a"])

    def test_turn_count_accuracy(self):
        self._write_lines([
            _line("user", "hi", 1, conversation_id="conv-1"),
            _line("assistant", "hello", 2, conversation_id="conv-1"),
            _line("user", "how are you", 3, conversation_id="conv-1"),
        ])

        resp = self.client.get("/conversations")
        groups = resp.get_json()
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["turn_count"], 3)
        self.assertEqual(groups[0]["first_ts"], 1)
        self.assertEqual(groups[0]["last_ts"], 3)

    def test_preview_is_first_user_role_text_truncated_to_80_chars(self):
        long_text = "x" * 200
        self._write_lines([
            _line("assistant", "should not be used as preview", 1, conversation_id="conv-1"),
            _line("user", long_text, 2, conversation_id="conv-1"),
            _line("user", "second user message, should not override preview", 3, conversation_id="conv-1"),
        ])

        resp = self.client.get("/conversations")
        groups = resp.get_json()
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["preview"], long_text[:80])
        self.assertEqual(len(groups[0]["preview"]), 80)

    def test_untagged_lines_are_skipped_and_do_not_create_bogus_groups(self):
        self._write_lines([
            _line("user", "no conversation id", 1),  # no conversation_id key
            _line("user", "tagged", 2, conversation_id="conv-1"),
        ])

        resp = self.client.get("/conversations")
        groups = resp.get_json()
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["conversation_id"], "conv-1")

    def test_conversation_with_no_user_message_has_null_preview(self):
        self._write_lines([
            _line("assistant", "only assistant text", 1, conversation_id="conv-1"),
        ])

        resp = self.client.get("/conversations")
        groups = resp.get_json()
        self.assertEqual(len(groups), 1)
        self.assertIsNone(groups[0]["preview"])

    def test_malformed_non_dict_lines_are_skipped_without_crashing(self):
        self._write_lines([
            "5",
            '"oops"',
            "[1, 2]",
            _line("user", "tagged", 1, conversation_id="conv-1"),
        ])

        resp = self.client.get("/conversations")
        self.assertEqual(resp.status_code, 200)
        groups = resp.get_json()
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["conversation_id"], "conv-1")

    def test_tagged_dict_missing_ts_is_skipped_without_crashing(self):
        entry_missing_ts = json.dumps({
            "role": "user",
            "text": "no timestamp here",
            "conversation_id": "conv-1",
        })
        self._write_lines([
            entry_missing_ts,
            _line("user", "has timestamp", 2, conversation_id="conv-2"),
        ])

        resp = self.client.get("/conversations")
        self.assertEqual(resp.status_code, 200)
        groups = resp.get_json()
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["conversation_id"], "conv-2")


if __name__ == "__main__":
    unittest.main()
