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
        classify_response = self._prepare_response(payload)
        chat_response = MagicMock()
        chat_response.choices = [FakeChoice("It's a lovely day, sir.")]
        self.mock_client.chat.completions.create.side_effect = [classify_response, chat_response]

        result = self.brain.think("hi jarvis")

        self.assertEqual(result["intent"], "chat")
        self.assertEqual(result["reply"], "It's a lovely day, sir.")
        self.assertEqual(self.mock_client.chat.completions.create.call_count, 2)

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
        # Final resolved intent is open_app, not chat, so generate_chat_reply
        # must not fire and there must be no third call.
        self.assertEqual(self.mock_client.chat.completions.create.call_count, 2)

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

    @patch("brain.retrieve", return_value=[])
    def test_think_calls_generate_chat_reply_for_chat_intent(self, mock_retrieve):
        classify_payload = json.dumps({"intent": "chat", "params": {}, "reply": "Hello sir."})
        classify_response = self._prepare_response(classify_payload)
        chat_response = MagicMock()
        chat_response.choices = [FakeChoice("How can I help further, sir?")]
        self.mock_client.chat.completions.create.side_effect = [classify_response, chat_response]

        result = self.brain.think("hi jarvis")

        self.assertEqual(result["reply"], "How can I help further, sir?")
        self.assertEqual(self.mock_client.chat.completions.create.call_count, 2)

        first_call_kwargs = self.mock_client.chat.completions.create.call_args_list[0][1]
        second_call_kwargs = self.mock_client.chat.completions.create.call_args_list[1][1]

        self.assertEqual(first_call_kwargs["response_format"], {"type": "json_object"})
        self.assertEqual(first_call_kwargs["messages"][0]["content"], brain.JARVIS_SYSTEM)

        self.assertNotIn("response_format", second_call_kwargs)
        self.assertEqual(second_call_kwargs["messages"][0]["content"], brain.CHAT_SYSTEM)

    def test_generate_chat_reply_appends_to_history_and_returns_content(self):
        self.brain.history = [{"role": "user", "content": "hello there"}]
        response = MagicMock()
        response.choices = [FakeChoice("Good day, sir.")]
        self.mock_client.chat.completions.create.return_value = response

        reply = self.brain.generate_chat_reply("hello there")

        self.assertEqual(reply, "Good day, sir.")
        self.assertEqual(self.brain.history[-1], {"role": "assistant", "content": "Good day, sir."})

    def test_think_does_not_call_generate_chat_reply_for_non_chat_intent(self):
        payload = json.dumps({"intent": "get_time", "params": {}, "reply": "It's noon, sir."})
        self._prepare_response(payload)

        result = self.brain.think("what time is it")

        self.assertEqual(result, {"intent": "get_time", "params": {}, "reply": "It's noon, sir."})
        self.mock_client.chat.completions.create.assert_called_once()

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

    # ── Sticky task-domain escalation ────────────────────────────────────

    def test_init_last_intent_is_none(self):
        self.assertIsNone(self.brain.last_intent)

    def test_think_sets_last_intent_to_result_intent(self):
        payload = json.dumps({"intent": "get_time", "params": {}, "reply": "It's noon, sir."})
        self._prepare_response(payload)

        self.brain.think("what time is it")

        self.assertEqual(self.brain.last_intent, "get_time")

    def test_think_sets_last_intent_to_chat_on_chat_result(self):
        classify_payload = json.dumps({"intent": "chat", "params": {}, "reply": "Hello sir."})
        classify_response = self._prepare_response(classify_payload)
        chat_response = MagicMock()
        chat_response.choices = [FakeChoice("How can I help further, sir?")]
        self.mock_client.chat.completions.create.side_effect = [classify_response, chat_response]

        self.brain.think("hi jarvis")

        self.assertEqual(self.brain.last_intent, "chat")

    def test_think_escalates_when_last_intent_was_task_domain_no_keyword(self):
        # No action keyword in the user text at all - only the sticky
        # last_intent from the previous turn should trigger escalation.
        self.brain.last_intent = "daily_task_reminder"

        first_payload = json.dumps({"intent": "chat", "params": {}, "reply": "Not sure."})
        second_payload = json.dumps(
            {"intent": "manage_task", "params": {"action": "done", "query": "first"},
             "reply": "Marking it done."}
        )
        first_response = self._prepare_response(first_payload)
        second_response = MagicMock()
        second_response.choices = [FakeChoice(second_payload)]
        self.mock_client.chat.completions.create.side_effect = [first_response, second_response]

        result = self.brain.think("mark the first one done")

        self.assertEqual(result["intent"], "manage_task")
        self.assertEqual(self.mock_client.chat.completions.create.call_count, 2)
        second_call_model = self.mock_client.chat.completions.create.call_args_list[1][1]["model"]
        self.assertEqual(second_call_model, "gpt-4o")
        self.assertEqual(self.brain.last_intent, "manage_task")

    def test_think_escalates_when_last_intent_was_manage_task(self):
        self.brain.last_intent = "manage_task"

        first_payload = json.dumps({"intent": "chat", "params": {}, "reply": "Not sure."})
        second_payload = json.dumps(
            {"intent": "manage_task", "params": {"action": "add", "description": "call mom"},
             "reply": "Adding it."}
        )
        first_response = self._prepare_response(first_payload)
        second_response = MagicMock()
        second_response.choices = [FakeChoice(second_payload)]
        self.mock_client.chat.completions.create.side_effect = [first_response, second_response]

        result = self.brain.think("also add call mom")

        self.assertEqual(result["intent"], "manage_task")
        self.assertEqual(self.mock_client.chat.completions.create.call_count, 2)

    def test_think_does_not_escalate_without_sticky_intent_or_keyword(self):
        # No prior task-domain intent, no action keyword - result should
        # stay at one call (chat), matching prior (non-sticky) behavior.
        payload = json.dumps({"intent": "chat", "params": {}, "reply": "Not sure."})
        classify_response = self._prepare_response(payload)
        chat_response = MagicMock()
        chat_response.choices = [FakeChoice("Could you clarify, sir?")]
        self.mock_client.chat.completions.create.side_effect = [classify_response, chat_response]

        self.brain.think("tell me something interesting")

        # Only the classify call + the chat-reply call - no escalation call.
        self.assertEqual(self.mock_client.chat.completions.create.call_count, 2)

    def test_last_intent_stops_forcing_escalation_after_intervening_unrelated_intent(self):
        # Turn 1: task-domain intent sets last_intent.
        payload1 = json.dumps({"intent": "daily_task_reminder", "params": {}, "reply": "Checking, sir."})
        self._prepare_response(payload1)
        self.brain.think("what's on my todo list")
        self.assertEqual(self.brain.last_intent, "daily_task_reminder")

        # Turn 2: an unrelated intent (chat, no keyword). Since last_intent
        # is still "daily_task_reminder" going into this turn, it still
        # gets the one extra escalation attempt (both attempts land on
        # chat) - but last_intent must update to "chat" afterward, not stay
        # stuck on the task-domain value.
        classify_payload = json.dumps({"intent": "chat", "params": {}, "reply": "Hello."})
        classify_response = self._prepare_response(classify_payload)
        escalate_response = MagicMock()
        escalate_response.choices = [FakeChoice(classify_payload)]
        chat_response = MagicMock()
        chat_response.choices = [FakeChoice("Good day, sir.")]
        self.mock_client.chat.completions.create.side_effect = [
            classify_response, escalate_response, chat_response
        ]
        self.brain.think("what a nice day")
        self.assertEqual(self.brain.last_intent, "chat")

        # Turn 3: another ambiguous chat turn with no keyword - must NOT
        # escalate anymore, since last_intent is no longer task-domain.
        payload3 = json.dumps({"intent": "chat", "params": {}, "reply": "Not sure."})
        classify_response3 = self._prepare_response(payload3)
        chat_response3 = MagicMock()
        chat_response3.choices = [FakeChoice("Could you clarify, sir?")]
        self.mock_client.chat.completions.create.side_effect = [classify_response3, chat_response3]
        calls_before = self.mock_client.chat.completions.create.call_count
        self.brain.think("hmm okay")

        # Only 2 more calls (classify + chat reply) - no escalation call.
        self.assertEqual(
            self.mock_client.chat.completions.create.call_count - calls_before, 2
        )


if __name__ == "__main__":
    unittest.main()
