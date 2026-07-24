"""
test/test_new_conversation.py — Sanity check for jarvis/state.py's
request_history_reset() / consume_history_reset() cross-process signal.

Verifies the signal file is created on request, consumed exactly once, and
that consuming it is safe even when the file never existed or has already
been removed by a concurrent consumer.
"""

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


class TestHistoryResetSignal(unittest.TestCase):

    def setUp(self):
        self._orig_file = state_module.RESET_SIGNAL_FILE
        fd, self._tmp_path = __import__("tempfile").mkstemp(suffix=".reset")
        os.close(fd)
        os.remove(self._tmp_path)  # start from a non-existent file
        state_module.RESET_SIGNAL_FILE = self._tmp_path

    def tearDown(self):
        state_module.RESET_SIGNAL_FILE = self._orig_file
        if os.path.exists(self._tmp_path):
            os.remove(self._tmp_path)

    def test_request_creates_file(self):
        self.assertFalse(os.path.exists(self._tmp_path))
        state_module.request_history_reset()
        self.assertTrue(os.path.exists(self._tmp_path))

    def test_consume_returns_true_once_then_false(self):
        state_module.request_history_reset()

        self.assertTrue(state_module.consume_history_reset())
        self.assertFalse(os.path.exists(self._tmp_path))
        self.assertFalse(state_module.consume_history_reset())

    def test_consume_returns_false_when_never_requested(self):
        self.assertFalse(os.path.exists(self._tmp_path))
        self.assertFalse(state_module.consume_history_reset())

    def test_consume_does_not_raise_if_file_already_gone(self):
        state_module.request_history_reset()
        # Simulate a concurrent consumer removing the file first.
        os.remove(self._tmp_path)
        # Recreate so os.path.exists() sees it, then delete right before
        # os.remove() would run is hard to simulate deterministically; the
        # important guarantee is that a missing file never raises.
        try:
            result = state_module.consume_history_reset()
        except OSError:
            self.fail("consume_history_reset() raised OSError unexpectedly")
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
