"""
tools/test_conversation.py - Manual end-to-end conversation test.

Uses OpenAI to play the "user" side of a conversation, sends each generated
message to the running JARVIS UI server's /chat endpoint, and speaks each
reply out loud via the real TTS fallback chain (tts.Speaker).

Requires: `python ui/server.py` already running (default port 5151).

Usage:
    python tools/test_conversation.py
    python tools/test_conversation.py --turns 5 --topic "planning a trip to Japan"
    python tools/test_conversation.py --port 5151 --no-speak
"""

import argparse
import os
import sys
import tempfile

import openai
import requests
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

load_dotenv()

_USER_SYSTEM = (
    "You are role-playing as a person having a casual voice conversation with "
    "their AI assistant JARVIS. Topic: {topic}. Reply with ONLY what you'd say "
    "next, one short conversational turn (like natural speech, not an essay). "
    "Never mention you are an AI."
)


def generate_user_turn(client, topic, history):
    messages = [{"role": "system", "content": _USER_SYSTEM.format(topic=topic)}]
    # Flip roles: JARVIS's replies become "user" turns to this model, and this
    # model's own prior turns become "assistant" turns, so it keeps context.
    for turn in history:
        messages.append({"role": "assistant" if turn["role"] == "user" else "user",
                          "content": turn["content"]})
    resp = client.chat.completions.create(model="gpt-4o-mini", messages=messages)
    return resp.choices[0].message.content.strip()


class UserVoice:
    """Speaks the simulated user's lines through pyttsx3 with a voice
    distinct from Speaker's jarvis-cloned voice, so the two sides of the
    conversation are audibly different in the recording/live playback."""

    def __init__(self):
        import pyttsx3
        self._engine = pyttsx3.init()
        self._engine.setProperty("rate", 175)
        voices = self._engine.getProperty("voices")
        # Prefer a female-sounding voice to contrast with JARVIS's male voice.
        for name in ["zira", "hazel", "susan", "female"]:
            for v in voices:
                if name in v.name.lower():
                    self._engine.setProperty("voice", v.id)
                    break

    def speak(self, text):
        import sounddevice as sd
        from scipy.io import wavfile

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name
        self._engine.save_to_file(text, tmp_path)
        self._engine.runAndWait()
        rate, data = wavfile.read(tmp_path)
        sd.play(data, samplerate=rate)
        sd.wait()
        os.remove(tmp_path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--turns", type=int, default=4, help="number of user turns")
    ap.add_argument("--topic", default="what to do this weekend")
    ap.add_argument("--port", type=int, default=int(os.getenv("JARVIS_UI_PORT", "5151")))
    ap.add_argument("--no-speak", action="store_true", help="skip TTS playback")
    args = ap.parse_args()

    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    speaker = None
    user_voice = None
    if not args.no_speak:
        from tts import Speaker
        speaker = Speaker()
        user_voice = UserVoice()

    base_url = "http://127.0.0.1:{}".format(args.port)
    history = []  # what the simulated user said/heard, for generate_user_turn's context

    for i in range(args.turns):
        user_text = generate_user_turn(client, args.topic, history)
        print("user> {}".format(user_text))
        history.append({"role": "user", "content": user_text})
        if user_voice is not None:
            user_voice.speak(user_text)

        # No conversation_id needed - /chat keeps its own server-side brain
        # history across calls within the same server process.
        resp = requests.post("{}/chat".format(base_url), json={"message": user_text}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        reply = data["reply"]
        print("jarvis> {} [{}]".format(reply, data.get("intent")))
        history.append({"role": "assistant", "content": reply})

        if speaker is not None:
            speaker.speak(reply)

    print("\nDone: {} turns.".format(args.turns))


if __name__ == "__main__":
    main()
