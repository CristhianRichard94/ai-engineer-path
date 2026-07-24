"""
test/test_chat_route.py — Flask test-client coverage for ui/server.py's
POST /chat route.

Verifies request validation (missing/empty/non-string/oversized message),
the happy path (brain.think -> router.dispatch -> transcript append ->
JSON reply), that vault write failures never fail the request, and that
brain/router exceptions are caught and never leak internals to the
response body.

All external side-effects (OpenAI client construction, IntentRouter's own
external deps) are mocked so the test suite runs without real network
access or hardware.
"""

import os
import sys
import threading
import time
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

# Stub heavy optional packages before importing router/server so we never
# need them installed in the test environment (mirrors test_router.py).
from unittest.mock import MagicMock  # noqa: E402
for mod in ("pycaw", "pycaw.pycaw", "comtypes", "spotipy",
            "spotipy.oauth2", "spotipy.exceptions", "anthropic", "openai"):
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

import state as state_module  # noqa: E402
import server as server_module  # noqa: E402


class TestChatRoute(unittest.TestCase):

    def setUp(self):
        self._orig_transcript_file = state_module.TRANSCRIPT_FILE
        self._orig_server_transcript_file = server_module.TRANSCRIPT_FILE
        fd, self._tmp_transcript = __import__("tempfile").mkstemp(suffix=".jsonl")
        os.close(fd)
        os.remove(self._tmp_transcript)
        state_module.TRANSCRIPT_FILE = self._tmp_transcript
        # server.py imports TRANSCRIPT_FILE as its own module-level name
        # (used by _read_transcript/_resume_conversation), so it must be
        # patched separately from state_module's copy.
        server_module.TRANSCRIPT_FILE = self._tmp_transcript

        # Reset the module-level shared brain/router singletons between
        # tests so mocks don't leak across cases.
        server_module._brain = None
        server_module._router = None

        self.client = server_module.app.test_client()

    def tearDown(self):
        state_module.TRANSCRIPT_FILE = self._orig_transcript_file
        server_module.TRANSCRIPT_FILE = self._orig_server_transcript_file
        if os.path.exists(self._tmp_transcript):
            os.remove(self._tmp_transcript)
        server_module._brain = None
        server_module._router = None

    def _mock_components(self, parsed=None, reply="Done, sir."):
        mock_brain = MagicMock()
        mock_brain.conversation_id = "test-conversation-id"
        mock_brain.think.return_value = parsed or {"intent": "chat", "params": {}, "reply": reply}
        mock_router = MagicMock()
        mock_router.dispatch.return_value = reply
        return mock.patch.object(
            server_module, "_get_chat_components", return_value=(mock_brain, mock_router)
        ), mock_brain, mock_router

    # ── Happy path ──────────────────────────────────────────────────────

    def test_happy_path_returns_reply_and_intent(self):
        patcher, mock_brain, mock_router = self._mock_components(
            parsed={"intent": "get_time", "params": {}, "reply": "It is noon, sir."},
            reply="It is noon, sir.",
        )
        with patcher, mock.patch.object(server_module, "write_session_note") as mock_note:
            resp = self.client.post("/chat", json={"message": "what time is it"})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"reply": "It is noon, sir.", "intent": "get_time"})
        mock_brain.think.assert_called_once_with("what time is it")
        mock_router.dispatch.assert_called_once_with(
            mock_brain.think.return_value, raw_text="what time is it"
        )
        mock_note.assert_called_once_with("get_time", "what time is it", "It is noon, sir.")

    def test_happy_path_appends_transcript(self):
        patcher, _, _ = self._mock_components()
        with patcher, mock.patch.object(server_module, "write_session_note"):
            self.client.post("/chat", json={"message": "hello"})

        with open(self._tmp_transcript, "r", encoding="utf-8") as f:
            lines = [line for line in f.read().splitlines() if line]
        self.assertEqual(len(lines), 2)
        self.assertIn('"role": "user"', lines[0])
        self.assertIn('"hello"', lines[0])
        self.assertIn('"role": "assistant"', lines[1])

    def test_vault_write_failure_does_not_fail_request(self):
        patcher, _, _ = self._mock_components()
        with patcher, mock.patch.object(
            server_module, "write_session_note", side_effect=OSError("disk full")
        ):
            resp = self.client.post("/chat", json={"message": "hello"})

        self.assertEqual(resp.status_code, 200)

    # ── Validation ──────────────────────────────────────────────────────

    def test_missing_message_returns_400(self):
        resp = self.client.post("/chat", json={})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    def test_empty_message_returns_400(self):
        resp = self.client.post("/chat", json={"message": "   "})
        self.assertEqual(resp.status_code, 400)

    def test_non_string_message_returns_400(self):
        resp = self.client.post("/chat", json={"message": 123})
        self.assertEqual(resp.status_code, 400)

    def test_oversized_message_returns_400(self):
        resp = self.client.post("/chat", json={"message": "a" * 4001})
        self.assertEqual(resp.status_code, 400)

    def test_non_json_body_returns_400(self):
        resp = self.client.post("/chat", data="not json", content_type="text/plain")
        self.assertEqual(resp.status_code, 400)

    def test_json_array_body_returns_400(self):
        resp = self.client.post("/chat", json=["not", "a", "dict"])
        self.assertEqual(resp.status_code, 400)

    # ── Error handling ──────────────────────────────────────────────────

    def test_brain_exception_returns_500_without_leaking_internals(self):
        mock_brain = MagicMock()
        mock_brain.think.side_effect = RuntimeError(
            "API key invalid at C:\\Users\\secret\\.env"
        )
        mock_router = MagicMock()
        with mock.patch.object(
            server_module, "_get_chat_components", return_value=(mock_brain, mock_router)
        ):
            resp = self.client.post("/chat", json={"message": "hello"})

        self.assertEqual(resp.status_code, 500)
        body = resp.get_json()
        self.assertIn("error", body)
        self.assertNotIn("secret", str(body))
        self.assertNotIn("C:\\", str(body))
        self.assertNotIn("Traceback", str(body))

    def test_router_exception_returns_500_without_leaking_internals(self):
        mock_brain = MagicMock()
        mock_brain.think.return_value = {"intent": "chat", "params": {}, "reply": "ok"}
        mock_router = MagicMock()
        mock_router.dispatch.side_effect = RuntimeError("boom at /secret/path")
        with mock.patch.object(
            server_module, "_get_chat_components", return_value=(mock_brain, mock_router)
        ):
            resp = self.client.post("/chat", json={"message": "hello"})

        self.assertEqual(resp.status_code, 500)
        body = resp.get_json()
        self.assertIn("error", body)
        self.assertNotIn("/secret/path", str(body))

    # ── Concurrency ─────────────────────────────────────────────────────

    def test_concurrent_requests_preserve_transcript_ordering(self):
        """Two overlapping /chat requests must never interleave their
        user/assistant transcript lines - each turn's pair must stay
        adjacent and in order, validating that append_transcript runs
        inside the same lock as think()/dispatch()."""
        mock_brain = MagicMock()
        mock_brain.conversation_id = "test-conversation-id"

        def think(message):
            # Simulate a slow LLM call so the two requests are guaranteed
            # to overlap in time.
            time.sleep(0.05)
            return {"intent": "chat", "params": {}, "reply": "reply-for-" + message}

        mock_brain.think.side_effect = think

        mock_router = MagicMock()
        mock_router.dispatch.side_effect = lambda parsed, raw_text=None: parsed["reply"]

        results = {}

        def make_request(name):
            # Each thread uses its own test client - the Flask test client
            # is not safe to share across threads for concurrent requests.
            client = server_module.app.test_client()
            resp = client.post("/chat", json={"message": name})
            results[name] = resp.status_code

        # Patch once for the whole test (not per-thread) - entering/exiting
        # mock.patch.object concurrently from two threads on the same
        # target is itself a race and can transiently restore the real
        # (unmocked) function mid-flight.
        with mock.patch.object(
            server_module, "_get_chat_components", return_value=(mock_brain, mock_router)
        ), mock.patch.object(server_module, "write_session_note"):
            t1 = threading.Thread(target=make_request, args=("alpha",))
            t2 = threading.Thread(target=make_request, args=("beta",))
            t1.start()
            t2.start()
            t1.join(timeout=5)
            t2.join(timeout=5)

        self.assertEqual(results.get("alpha"), 200)
        self.assertEqual(results.get("beta"), 200)

        with open(self._tmp_transcript, "r", encoding="utf-8") as f:
            lines = [line for line in f.read().splitlines() if line]

        self.assertEqual(len(lines), 4)
        # Each turn's user line must be immediately followed by its own
        # assistant reply - never another turn's user/assistant line.
        for i in (0, 2):
            user_line = lines[i]
            assistant_line = lines[i + 1]
            self.assertIn('"role": "user"', user_line)
            self.assertIn('"role": "assistant"', assistant_line)
            name = "alpha" if '"alpha"' in user_line else "beta"
            self.assertIn(name, user_line)
            self.assertIn("reply-for-" + name, assistant_line)

    def test_exception_does_not_append_transcript(self):
        mock_brain = MagicMock()
        mock_brain.think.side_effect = RuntimeError("boom")
        mock_router = MagicMock()
        with mock.patch.object(
            server_module, "_get_chat_components", return_value=(mock_brain, mock_router)
        ):
            self.client.post("/chat", json={"message": "hello"})

        self.assertFalse(os.path.exists(self._tmp_transcript))

    # ── Resume conversation ─────────────────────────────────────────────

    def _write_transcript_lines(self, entries):
        with open(self._tmp_transcript, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(__import__("json").dumps(entry) + "\n")

    def test_resume_id_reconstructs_history_from_transcript(self):
        self._write_transcript_lines([
            {"role": "user", "text": "first", "ts": 1, "conversation_id": "old-conv"},
            {"role": "assistant", "text": "reply-first", "ts": 2, "conversation_id": "old-conv"},
            {"role": "user", "text": "unrelated", "ts": 3, "conversation_id": "other-conv"},
        ])

        patcher, mock_brain, mock_router = self._mock_components()
        mock_brain.conversation_id = "current-conv"
        mock_brain.max_history = 10
        with patcher, mock.patch.object(server_module, "write_session_note"):
            resp = self.client.post(
                "/chat", json={"message": "hello", "conversation_id": "old-conv"}
            )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(mock_brain.conversation_id, "old-conv")
        self.assertEqual(
            mock_brain.history,
            [
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "reply-first"},
            ],
        )

    def test_resume_id_caps_history_to_max_history_turns(self):
        entries = []
        for i in range(5):
            entries.append({"role": "user", "text": "u{}".format(i), "ts": i, "conversation_id": "old-conv"})
            entries.append({"role": "assistant", "text": "a{}".format(i), "ts": i, "conversation_id": "old-conv"})
        self._write_transcript_lines(entries)

        patcher, mock_brain, mock_router = self._mock_components()
        mock_brain.conversation_id = "current-conv"
        mock_brain.max_history = 3
        with patcher, mock.patch.object(server_module, "write_session_note"):
            resp = self.client.post(
                "/chat", json={"message": "hello", "conversation_id": "old-conv"}
            )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mock_brain.history), 3)
        self.assertEqual(
            mock_brain.history,
            [
                {"role": "assistant", "content": "a3"},
                {"role": "user", "content": "u4"},
                {"role": "assistant", "content": "a4"},
            ],
        )

    def test_resume_id_matching_current_conversation_is_a_noop(self):
        patcher, mock_brain, mock_router = self._mock_components()
        mock_brain.conversation_id = "same-conv"
        mock_brain.max_history = 10
        mock_brain.history = ["preexisting"]
        with patcher, mock.patch.object(
            server_module, "_resume_conversation"
        ) as mock_resume, mock.patch.object(server_module, "write_session_note"):
            resp = self.client.post(
                "/chat", json={"message": "hello", "conversation_id": "same-conv"}
            )

        self.assertEqual(resp.status_code, 200)
        mock_resume.assert_not_called()

    def test_no_conversation_id_leaves_existing_behavior_unchanged(self):
        patcher, mock_brain, mock_router = self._mock_components()
        mock_brain.conversation_id = "current-conv"
        with patcher, mock.patch.object(
            server_module, "_resume_conversation"
        ) as mock_resume, mock.patch.object(server_module, "write_session_note"):
            resp = self.client.post("/chat", json={"message": "hello"})

        self.assertEqual(resp.status_code, 200)
        mock_resume.assert_not_called()

    def test_non_string_conversation_id_returns_400(self):
        resp = self.client.post("/chat", json={"message": "hello", "conversation_id": 123})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())


if __name__ == "__main__":
    unittest.main()
