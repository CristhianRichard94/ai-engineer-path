"""
test/test_new_conversation_route.py — Flask test-client coverage for
ui/server.py's POST /new-conversation route.

Verifies the route leaves transcript.jsonl untouched (it's now a
permanent append-only log; the route only resets the in-memory brain
history/conversation_id), raises the cross-process reset signal only when
a live JARVIS process is found (mirroring /restart's _do_restart()
liveness check via psutil.process_iter), responds
{"ok": true, "jarvis_running": bool}, and — unlike /restart's
_do_restart() — never calls subprocess.Popen or terminates/kills the
JARVIS process.
"""

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

import state as state_module  # noqa: E402
import server as server_module  # noqa: E402


class TestNewConversationRoute(unittest.TestCase):

    def setUp(self):
        self._orig_transcript = server_module.TRANSCRIPT_FILE
        self._orig_reset_file = state_module.RESET_SIGNAL_FILE

        fd, self._tmp_transcript = __import__("tempfile").mkstemp(suffix=".jsonl")
        os.close(fd)
        with open(self._tmp_transcript, "w", encoding="utf-8") as f:
            f.write('{"role": "user", "text": "hi", "ts": 1}\n')
            f.write('{"role": "assistant", "text": "hello, sir.", "ts": 2}\n')

        fd2, self._tmp_reset = __import__("tempfile").mkstemp(suffix=".reset")
        os.close(fd2)
        os.remove(self._tmp_reset)  # start from a non-existent signal file

        server_module.TRANSCRIPT_FILE = self._tmp_transcript
        state_module.RESET_SIGNAL_FILE = self._tmp_reset

        self._orig_brain = server_module._brain
        server_module._brain = None

        self.client = server_module.app.test_client()

    def tearDown(self):
        server_module.TRANSCRIPT_FILE = self._orig_transcript
        state_module.RESET_SIGNAL_FILE = self._orig_reset_file
        server_module._brain = self._orig_brain
        if os.path.exists(self._tmp_transcript):
            os.remove(self._tmp_transcript)
        if os.path.exists(self._tmp_reset):
            os.remove(self._tmp_reset)

    def test_does_not_touch_transcript_when_jarvis_running(self):
        with open(self._tmp_transcript, "r", encoding="utf-8") as f:
            original_content = f.read()
        self.assertGreater(len(original_content), 0)

        with mock.patch("server._jarvis_is_running", return_value=True):
            resp = self.client.post("/new-conversation")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"ok": True, "jarvis_running": True})
        with open(self._tmp_transcript, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), original_content)

    def test_does_not_touch_transcript_when_jarvis_not_running(self):
        with open(self._tmp_transcript, "r", encoding="utf-8") as f:
            original_content = f.read()
        self.assertGreater(len(original_content), 0)

        with mock.patch("server._jarvis_is_running", return_value=False):
            resp = self.client.post("/new-conversation")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"ok": True, "jarvis_running": False})
        with open(self._tmp_transcript, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), original_content)

    def test_raises_reset_signal_when_jarvis_running(self):
        self.assertFalse(os.path.exists(self._tmp_reset))

        with mock.patch("server._jarvis_is_running", return_value=True):
            self.client.post("/new-conversation")

        self.assertTrue(state_module.consume_history_reset())

    def test_does_not_raise_reset_signal_when_jarvis_not_running(self):
        # No live process means a stale signal file would just sit there
        # forever with no reader - a fresh process already starts with
        # empty brain.history, so there's nothing useful to signal.
        self.assertFalse(os.path.exists(self._tmp_reset))

        with mock.patch("server._jarvis_is_running", return_value=False):
            self.client.post("/new-conversation")

        self.assertFalse(os.path.exists(self._tmp_reset))

    def test_does_not_touch_popen(self):
        with mock.patch("server.subprocess.Popen") as mock_popen:
            resp = self.client.post("/new-conversation")

            self.assertEqual(resp.status_code, 200)
            mock_popen.assert_not_called()

    def test_liveness_check_uses_process_iter_like_restart(self):
        with mock.patch("server.psutil.process_iter", return_value=[]) as mock_process_iter:
            resp = self.client.post("/new-conversation")

            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.get_json()["jarvis_running"], False)
            mock_process_iter.assert_called_once()

    def test_resets_chat_brain_history_when_present(self):
        mock_brain = mock.MagicMock()
        server_module._brain = mock_brain

        with mock.patch("server._jarvis_is_running", return_value=False):
            resp = self.client.post("/new-conversation")

        self.assertEqual(resp.status_code, 200)
        mock_brain.reset_history.assert_called_once_with()

    def test_does_not_error_when_no_chat_brain_yet(self):
        server_module._brain = None

        with mock.patch("server._jarvis_is_running", return_value=False):
            resp = self.client.post("/new-conversation")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"ok": True, "jarvis_running": False})

    def test_reset_history_happens_while_chat_lock_is_held(self):
        mock_brain = mock.MagicMock()
        lock_states = []

        def spy_reset_history():
            lock_states.append(server_module._chat_lock.locked())

        mock_brain.reset_history.side_effect = spy_reset_history
        server_module._brain = mock_brain

        resp = self.client.post("/new-conversation")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(lock_states, [True])


if __name__ == "__main__":
    unittest.main()
