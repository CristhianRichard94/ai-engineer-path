"""
main.py - JARVIS entry point.

Session flow:
  1. Wait for "Hey JARVIS" wake word  (one-time per session)
  2. Acknowledge: "Yes, sir."
  3. Multi-turn conversation loop - NO wake word needed between commands
     a. Listen + transcribe
     b. Brain thinks -> structured JSON
     c. Router dispatches -> Windows / API action
     d. Speak reply
     e. If intent == "goodbye" -> end session, go back to step 1
  4. Repeat
"""

import os
import sys
import time
from dotenv import load_dotenv

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis"))

from wake_word import WakeWordDetector
from stt      import SpeechTranscriber
from tts      import Speaker
from brain    import JarvisBrain
from router   import IntentRouter
from state    import write_state

load_dotenv()

MAX_TURNS_PER_SESSION = 20   # safety cap before re-requesting wake word


def run_session(stt, brain, router, speaker):
    """Single conversation session (one wake-word activation)."""
    for turn in range(MAX_TURNS_PER_SESSION):
        # ── Listen ──────────────────────────────────────────────────
        command = stt.capture_and_transcribe()
        if not command:
            time.sleep(0.4)
            speaker.speak("I didn't catch that, sir.")
            continue

        # ── Think ───────────────────────────────────────────────────
        parsed = brain.think(command)
        intent = parsed.get("intent", "chat")

        # ── Dispatch ────────────────────────────────────────────────
        reply = router.dispatch(parsed, raw_text=command)

        # ── Speak ───────────────────────────────────────────────────
        # ponytail: Bluetooth headsets drop from A2DP (playback) to HFP
        # (mic) profile while capturing, then need a beat to switch back -
        # speaking immediately after listen can get silently swallowed.
        time.sleep(0.4)
        speaker.speak(reply)

        # ── Session end? ────────────────────────────────────────────
        if intent == "goodbye":
            return   # back to wake-word listening


def main():
    wake   = WakeWordDetector()
    stt    = SpeechTranscriber(api_key=os.getenv("OPENAI_API_KEY"))
    brain  = JarvisBrain(api_key=os.getenv("OPENAI_API_KEY"))
    router = IntentRouter()
    speaker = Speaker()

    speaker.speak("JARVIS online. At your service, sir.")

    try:
        while True:
            # ── Wait for "Hey JARVIS" ────────────────────────────
            wake.listen_for_wake()
            time.sleep(0.4)
            speaker.speak("Yes, sir.")

            # ── Conversation session ─────────────────────────────
            run_session(stt, brain, router, speaker)

    except KeyboardInterrupt:
        speaker.speak("Shutting down. Goodbye, sir.")
    finally:
        wake.cleanup()
        write_state("off")


if __name__ == "__main__":
    main()
