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

from wake_word import WakeWordDetector, NoMicrophoneError
from stt      import SpeechTranscriber
from tts      import Speaker
from brain    import JarvisBrain
from router   import IntentRouter
from state    import write_state, consume_history_reset
from vault    import ensure_vault_bootstrap, build_or_update_index, write_session_note

load_dotenv()

try:
    ensure_vault_bootstrap()
    build_or_update_index()
except Exception as e:
    print("[VAULT] Startup indexing failed, continuing without it: {}".format(e))

MAX_TURNS_PER_SESSION = 20   # safety cap before re-requesting wake word


def _apply_pending_history_reset(brain):
    """Check for a pending cross-process history-reset request and apply it.

    Returns True if a reset was pending (and has now been applied), else
    False. Shared by the wake-word loop and run_session() so there is a
    single place that consumes the signal and clears brain.history.
    """
    if consume_history_reset():
        brain.history = []
        return True
    return False


def run_session(stt, brain, router, speaker):
    """Single conversation session (one wake-word activation)."""
    for turn in range(MAX_TURNS_PER_SESSION):
        # ── New Conversation requested mid-session? ────────────────
        # Poll every turn (not just once before the session starts) so
        # clicking "New Conversation" actually interrupts a live,
        # multi-turn session instead of silently queuing until it ends.
        if _apply_pending_history_reset(brain):
            return   # back to wake-word listening

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

        # ── Persist session note (best-effort) ─────────────────────
        try:
            write_session_note(intent, command, reply)
        except Exception as e:
            print("[VAULT] Failed to write session note: {}".format(e))

        # ── Session end? ────────────────────────────────────────────
        if intent == "goodbye":
            try:
                build_or_update_index()
            except Exception as e:
                print("[VAULT] Failed to rebuild index at session end: {}".format(e))
            return   # back to wake-word listening


def main():
    try:
        wake = WakeWordDetector()
    except NoMicrophoneError as e:
        message = str(e)
        write_state("error", detail=message)
        print(message)
        sys.exit(1)

    stt    = SpeechTranscriber(api_key=os.getenv("OPENAI_API_KEY"))
    brain  = JarvisBrain(api_key=os.getenv("OPENAI_API_KEY"))
    router = IntentRouter()
    speaker = Speaker()

    speaker.speak("JARVIS online. At your service, sir.")

    try:
        while True:
            # ── Wait for "Hey JARVIS" ────────────────────────────
            wake.listen_for_wake()
            _apply_pending_history_reset(brain)
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
