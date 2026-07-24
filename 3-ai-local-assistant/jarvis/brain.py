import openai, json, uuid

from constants import JARVIS_SYSTEM, CHAT_SYSTEM
FALLBACK_INTENTS = {"chat"}   # intents that mean "mini wasn't sure"

class JarvisBrain:
    def __init__(self, api_key: str):
        self.client  = openai.OpenAI(api_key=api_key)
        self.history = []          # rolling conversation memory
        self.max_history = 10      # keep last 10 turns
        self.conversation_id = str(uuid.uuid4())   # identifies this conversation's lifetime

    def reset_history(self):
        """Clear rolling conversation memory and start a new conversation_id.

        Called whenever conversation history is reset (process restart, or
        an explicit "New Conversation" request) so transcript.jsonl lines
        written before/after this point can be told apart via
        conversation_id, even though they share the same brain instance.
        """
        self.history = []
        self.conversation_id = str(uuid.uuid4())

    def think(self, user_text: str) -> dict:
        result = self._call_model("gpt-4o-mini", user_text)

        # if mini defaulted to chat but the command sounds action-like,
        # escalate to gpt-4o for just this one call
        if result.get("intent") in FALLBACK_INTENTS and any(
            kw in user_text.lower()
            for kw in ["open", "close", "volume", "search", "folder", "system"]
        ):
            print("[BRAIN] Escalating to gpt-4o for ambiguous command...")
            result = self._call_model("gpt-4o", user_text)

        if result.get("intent") == "chat":
            result["reply"] = self.generate_chat_reply(user_text)

        return result

    def generate_chat_reply(self, user_text: str) -> str:
        """Genuine conversational reply for intent == 'chat', separate from the
        capped 'reply' field the classification call produces (tuned for
        <15-word action acks). Plain-text completion, reuses self.history."""
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": CHAT_SYSTEM},
                *self.history[-self.max_history:]
            ]
        )
        reply = response.choices[0].message.content
        self.history.append({"role": "assistant", "content": reply})
        return reply

    def _call_model(self, model: str, user_text: str) -> dict:
        self.history.append({"role": "user", "content": user_text})
        response = self.client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": JARVIS_SYSTEM},
                *self.history[-self.max_history:]
            ]
        )
        raw = response.choices[0].message.content
        self.history.append({"role": "assistant", "content": raw})
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"intent": "chat", "params": {}, "reply": "I didn't follow that, sir."}