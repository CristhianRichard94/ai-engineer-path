"""
test/test_main_session.py — Unit tests for main.py's run_session() and the
shared _apply_pending_history_reset() helper.

Verifies that a pending "New Conversation" request (jarvis/state.py's
consume_history_reset() signal) is polled on every turn of the live
listen/think/speak loop - not just once before the session starts - so
clicking New Conversation mid-conversation actually interrupts the running
session instead of silently queuing until it ends naturally.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
JARVIS_DIR = os.path.join(ROOT, "jarvis")
if JARVIS_DIR not in sys.path:
    sys.path.insert(0, JARVIS_DIR)

# main.py's module-level imports (wake_word, stt, etc.) pull in real audio
# libraries (sounddevice, scipy, openwakeword) - these are present in the
# project's venv (same as test_stt.py / test_wake_word.py rely on), so no
# stubbing is needed here. Stubbing them would pollute sys.modules for
# other test files in the same pytest run.
import main as main_module  # noqa: E402


class TestApplyPendingHistoryReset(unittest.TestCase):

    @patch("main.consume_history_reset", return_value=True)
    def test_clears_history_and_returns_true_when_reset_pending(self, mock_consume):
        brain = MagicMock()
        brain.history = ["some", "prior", "turns"]

        result = main_module._apply_pending_history_reset(brain)

        self.assertTrue(result)
        self.assertEqual(brain.history, [])

    @patch("main.consume_history_reset", return_value=False)
    def test_leaves_history_untouched_and_returns_false_when_no_reset(self, mock_consume):
        brain = MagicMock()
        brain.history = ["some", "prior", "turns"]

        result = main_module._apply_pending_history_reset(brain)

        self.assertFalse(result)
        self.assertEqual(brain.history, ["some", "prior", "turns"])


class TestRunSession(unittest.TestCase):

    def setUp(self):
        self.stt = MagicMock()
        self.brain = MagicMock()
        self.brain.history = ["turn1", "turn2"]
        self.router = MagicMock()
        self.speaker = MagicMock()

        self.stt.capture_and_transcribe.return_value = "what time is it"
        self.brain.think.return_value = {"intent": "get_time"}
        self.router.dispatch.return_value = "It is 3 PM, sir."

    @patch("main.write_session_note")
    @patch("main.build_or_update_index")
    @patch("main.time.sleep", return_value=None)
    @patch("main.consume_history_reset", return_value=True)
    def test_reset_pending_at_start_of_turn_ends_session_and_clears_history(
        self, mock_consume, mock_sleep, mock_build_index, mock_write_note
    ):
        main_module.run_session(self.stt, self.brain, self.router, self.speaker)

        # Session must end immediately - no listen/think/speak turn happens.
        self.stt.capture_and_transcribe.assert_not_called()
        self.brain.think.assert_not_called()
        self.router.dispatch.assert_not_called()
        self.speaker.speak.assert_not_called()
        self.assertEqual(self.brain.history, [])

    @patch("main.write_session_note")
    @patch("main.build_or_update_index")
    @patch("main.time.sleep", return_value=None)
    def test_reset_pending_mid_session_interrupts_before_next_turn(
        self, mock_sleep, mock_build_index, mock_write_note
    ):
        # Reset is not pending for the first turn, but becomes pending
        # before the second turn - simulating a click on New Conversation
        # while JARVIS is mid-conversation (e.g. speaking turn 1's reply).
        with patch("main.consume_history_reset", side_effect=[False, True]):
            main_module.run_session(self.stt, self.brain, self.router, self.speaker)

        # Exactly one full turn happened before the session was interrupted.
        self.assertEqual(self.stt.capture_and_transcribe.call_count, 1)
        self.assertEqual(self.router.dispatch.call_count, 1)
        self.assertEqual(self.brain.history, [])

    @patch("main.write_session_note")
    @patch("main.build_or_update_index")
    @patch("main.time.sleep", return_value=None)
    @patch("main.consume_history_reset", return_value=False)
    def test_no_reset_pending_runs_full_turn_normally(
        self, mock_consume, mock_sleep, mock_build_index, mock_write_note
    ):
        self.brain.think.return_value = {"intent": "goodbye"}

        main_module.run_session(self.stt, self.brain, self.router, self.speaker)

        self.stt.capture_and_transcribe.assert_called_once()
        self.speaker.speak.assert_called_with("It is 3 PM, sir.")
        # goodbye intent ends the session normally without touching history.
        self.assertEqual(self.brain.history, ["turn1", "turn2"])
        mock_write_note.assert_called_once_with("goodbye", "what time is it", "It is 3 PM, sir.")
        mock_build_index.assert_called_once()


if __name__ == "__main__":
    unittest.main()
