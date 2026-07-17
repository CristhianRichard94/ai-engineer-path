"""
test/test_state.py — Sanity check for jarvis/state.py's append_transcript().

Verifies each call appends exactly one valid JSON line with the expected
shape, without touching the repo's real transcript.jsonl.
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

import state as state_module


class TestAppendTranscript(unittest.TestCase):

    def setUp(self):
        self._orig_file = state_module.TRANSCRIPT_FILE
        fd, self._tmp_path = __import__("tempfile").mkstemp(suffix=".jsonl")
        os.close(fd)
        os.remove(self._tmp_path)  # start from a non-existent file, like a fresh run
        state_module.TRANSCRIPT_FILE = self._tmp_path

    def tearDown(self):
        state_module.TRANSCRIPT_FILE = self._orig_file
        if os.path.exists(self._tmp_path):
            os.remove(self._tmp_path)

    def test_appends_valid_json_line(self):
        state_module.append_transcript("user", "hello there")

        with open(self._tmp_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        self.assertEqual(len(lines), 1)
        entry = json.loads(lines[0])
        self.assertEqual(entry["role"], "user")
        self.assertEqual(entry["text"], "hello there")
        self.assertIn("ts", entry)

    def test_multiple_calls_append_multiple_lines(self):
        state_module.append_transcript("user", "hi")
        state_module.append_transcript("assistant", "hello, sir.")

        with open(self._tmp_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["role"], "user")
        self.assertEqual(json.loads(lines[1])["role"], "assistant")

    def test_skips_empty_text(self):
        state_module.append_transcript("user", "")
        self.assertFalse(os.path.exists(self._tmp_path))


if __name__ == "__main__":
    unittest.main()
