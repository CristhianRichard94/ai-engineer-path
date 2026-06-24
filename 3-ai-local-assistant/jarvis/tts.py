"""
tts.py - Text-to-speech for JARVIS.

Primary:  Fish Speech (local Docker container at http://localhost:8080)
Fallback: pyttsx3 (offline, no key required)

pyttsx3 NOTE: SAPI5 on Windows is NOT thread-safe; the engine lives in a
single dedicated worker thread.
"""

import io
import queue
import threading

import numpy as np
import requests
import sounddevice as sd
import soundfile as sf

FISH_SPEECH_URL = "http://localhost:8080"
FISH_SPEECH_TIMEOUT = 15  # seconds


class Speaker:

    def __init__(self):
        self._fish_available = self._check_fish_speech()

        # pyttsx3 fallback — dedicated thread (avoids SAPI5 re-init race)
        self._q = queue.Queue()
        self._worker = threading.Thread(target=self._pyttsx3_run, daemon=True)
        self._worker.start()

        if self._fish_available:
            print("[TTS] Fish Speech server online at {}".format(FISH_SPEECH_URL))
        else:
            print("[TTS] Fish Speech not reachable, using pyttsx3 fallback")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def speak(self, text: str):
        """Speak text and block until audio finishes."""
        print("[JARVIS] Speaking: {}".format(text))
        if self._fish_available:
            ok = self._fish_speak(text)
            if ok:
                return
            print("[TTS] Fish Speech failed, falling back to pyttsx3")

        done = threading.Event()
        self._q.put((text, done))
        done.wait()

    def speak_async(self, text: str):
        """Enqueue speech without waiting."""
        if self._fish_available:
            threading.Thread(
                target=self._fish_speak_safe,
                args=(text,),
                daemon=True,
            ).start()
        else:
            self._q.put((text, None))

    # ------------------------------------------------------------------
    # Fish Speech
    # ------------------------------------------------------------------

    def _check_fish_speech(self) -> bool:
        try:
            r = requests.get(
                "{}/v1/health".format(FISH_SPEECH_URL),
                timeout=2,
            )
            return r.status_code == 200
        except Exception:
            return False

    def _fish_speak(self, text: str) -> bool:
        """POST to Fish Speech, play returned audio. Returns True on success."""
        try:
            resp = requests.post(
                "{}/v1/tts".format(FISH_SPEECH_URL),
                json={
                    "text": text,
                    "reference_id": "jarvis",   # matches tools/voice/references/jarvis/
                    "format": "wav",
                    "streaming": False,
                },
                timeout=FISH_SPEECH_TIMEOUT,
            )
            resp.raise_for_status()

            audio_data, samplerate = sf.read(io.BytesIO(resp.content), dtype="float32")
            sd.play(audio_data, samplerate=samplerate)
            sd.wait()
            return True
        except Exception as exc:
            print("[TTS] Fish Speech error: {}".format(exc))
            return False

    def _fish_speak_safe(self, text: str):
        ok = self._fish_speak(text)
        if not ok:
            done = threading.Event()
            self._q.put((text, done))
            done.wait()

    # ------------------------------------------------------------------
    # pyttsx3 worker
    # ------------------------------------------------------------------

    def _pyttsx3_run(self):
        """Single thread that owns the pyttsx3 engine for its whole lifetime."""
        import pyttsx3
        engine = pyttsx3.init()
        self._configure_engine(engine)

        while True:
            item = self._q.get()
            if item is None:       # shutdown sentinel
                break
            text, done_event = item
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception as exc:
                print("[TTS] pyttsx3 error: {}".format(exc))
            if done_event is not None:
                done_event.set()

    @staticmethod
    def _configure_engine(engine):
        engine.setProperty('rate', 165)
        engine.setProperty('volume', 1.0)
        voices = engine.getProperty('voices')
        for name in ["guy", "mark", "david", "james"]:
            for v in voices:
                if name in v.name.lower():
                    engine.setProperty('voice', v.id)
                    print("[TTS] pyttsx3 voice: {}".format(v.name))
                    return
        if voices:
            engine.setProperty('voice', voices[0].id)
