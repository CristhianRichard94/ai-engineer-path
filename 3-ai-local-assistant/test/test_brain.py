import os
import sys
import json
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Ensure the project root is on sys.path so test imports work from the test folder.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
JARVIS_DIR = os.path.join(ROOT, "jarvis")
if JARVIS_DIR not in sys.path:
    sys.path.insert(0, JARVIS_DIR)

# Provide a fake openai module while importing brain so tests do not require the real package.
if "openai" not in sys.modules:
    sys.modules["openai"] = MagicMock()

import brain


class FakeChoice:
    def __init__(self, content):
        self.message = SimpleNamespace(content=content)


class JarvisBrainTests(unittest.TestCase):
    def setUp(self):
        self.api_key = "test-key"
        self.mock_client = MagicMock()
        self.mock_client.chat.completions.create = MagicMock()
        self.openai_patcher = patch("brain.openai.OpenAI", return_value=self.mock_client)
        self.mock_openai = self.openai_patcher.start()
        self.brain = brain.JarvisBrain(api_key=self.api_key)

    def tearDown(self):
        self.openai_patcher.stop()

    def _prepare_response(self, content):
        response = MagicMock()
        response.choices = [FakeChoice(content)]
        self.mock_client.chat.completions.create.return_value = response
        return response

    def test_think_returns_parsed_json_result(self):
        payload = json.dumps({"intent": "chat", "params": {}, "reply": "Hello sir."})
        self._prepare_response(payload)

        result = self.brain.think("hi jarvis")

        self.assertEqual(result, {"intent": "chat", "params": {}, "reply": "Hello sir."})
        self.mock_client.chat.completions.create.assert_called_once()

    def test_think_escalates_when_fallback_intent_and_action_keyword(self):
        first_payload = json.dumps({"intent": "chat", "params": {}, "reply": "I am not sure."})
        second_payload = json.dumps({"intent": "open_app", "params": {"app": "notepad"}, "reply": "Opening notepad."})

        first_response = self._prepare_response(first_payload)
        second_response = MagicMock()
        second_response.choices = [FakeChoice(second_payload)]
        self.mock_client.chat.completions.create.side_effect = [first_response, second_response]

        result = self.brain.think("open notepad")

        self.assertEqual(result, {"intent": "open_app", "params": {"app": "notepad"}, "reply": "Opening notepad."})
        self.assertEqual(self.mock_client.chat.completions.create.call_count, 2)
        first_call_model = self.mock_client.chat.completions.create.call_args_list[0][1]["model"]
        second_call_model = self.mock_client.chat.completions.create.call_args_list[1][1]["model"]
        self.assertEqual(first_call_model, "gpt-4o-mini")
        self.assertEqual(second_call_model, "gpt-4o")

    def test_call_model_returns_fallback_chat_when_invalid_json(self):
        self._prepare_response("not valid json")

        result = self.brain._call_model("gpt-4o-mini", "hello")

        self.assertEqual(result, {"intent": "chat", "params": {}, "reply": "I didn't follow that, sir."})
        self.mock_client.chat.completions.create.assert_called_once()

    def test_call_model_records_history_and_trims_to_max_history(self):
        # Prepopulate history longer than max_history to verify trimming behavior.
        for i in range(15):
            self.brain.history.append({"role": "user", "content": f"turn {i}"})

        payload = json.dumps({"intent": "chat", "params": {}, "reply": "ok."})
        self._prepare_response(payload)

        self.brain._call_model("gpt-4o-mini", "latest command")

        self.assertEqual(len(self.brain.history), 17)
        call_args = self.mock_client.chat.completions.create.call_args[1]
        sent_messages = call_args["messages"]
        self.assertEqual(sent_messages[0]["role"], "system")
        self.assertEqual(len(sent_messages) - 1, self.brain.max_history)
        self.assertEqual(sent_messages[-1]["content"], "latest command")

    # ── conversation_id ────────────────────────────────────────────────

    def test_init_generates_valid_uuid_conversation_id(self):
        self.assertIsInstance(self.brain.conversation_id, str)
        uuid.UUID(self.brain.conversation_id)  # raises ValueError if invalid

    def test_reset_history_clears_history_and_regenerates_conversation_id(self):
        self.brain.history = [{"role": "user", "content": "hi"}]
        original_id = self.brain.conversation_id

        self.brain.reset_history()

        self.assertEqual(self.brain.history, [])
        self.assertNotEqual(self.brain.conversation_id, original_id)
        uuid.UUID(self.brain.conversation_id)

    def test_two_instances_get_different_conversation_ids(self):
        other_brain = brain.JarvisBrain(api_key=self.api_key)
        self.assertNotEqual(self.brain.conversation_id, other_brain.conversation_id)


if __name__ == "__main__":
    unittest.main()
