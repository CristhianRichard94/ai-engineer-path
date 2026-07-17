"""
tts.py - Text-to-speech for JARVIS.

Fallback chain (tries each in order):
  1. Fish Speech  — local Docker container (localhost:8080), JARVIS voice clone
  2. ElevenLabs   — cloud API, high-quality voice (ELEVENLABS_API_KEY required)
  3. pyttsx3      — fully offline, Windows SAPI5

Fish Speech runs as a Docker container:
    cd tools/voice
    docker compose -f docker-compose.jarvis.yml up -d

ElevenLabs keys go in .env:
    ELEVENLABS_API_KEY=...
    ELEVENLABS_VOICE_ID=...
"""

import os
import sys
import io
import queue
import threading

import numpy as np
import sounddevice as sd

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis"))
from state import write_state


# ── Fish Speech config ───────────────────────────────────────────────────────
_FISH_URL        = os.getenv("FISH_SPEECH_URL", "http://localhost:8080")
_FISH_VOICE_ID   = "jarvis"          # references/jarvis/ folder inside the container
_FISH_TIMEOUT    = 20                # seconds to wait for inference


class Speaker:

    def __init__(self):
        self._el_key   = os.getenv("ELEVENLABS_API_KEY", "").strip()
        self._el_voice = os.getenv("ELEVENLABS_VOICE_ID", "").strip()

        # Fish Speech availability is checked lazily (server may start after JARVIS)
        self._fish_ok  = None   # None = unknown, True/False = tested

        # pyttsx3 worker thread (last resort — SAPI5 must live in one thread)
        self._q      = queue.Queue()
        self._worker = threading.Thread(target=self._pyttsx3_run, daemon=True)
        self._worker.start()

        self._log_config()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def speak(self, text: str):
        """Speak text; block until audio finishes."""
        print("[JARVIS] Speaking: {}".format(text))
        write_state("speaking", detail=text)

        if self._try_fish_speech(text):
            return
        if self._try_elevenlabs(text):
            return
        self._pyttsx3_speak(text)

    def speak_async(self, text: str):
        """Enqueue speech without waiting."""
        threading.Thread(target=self.speak, args=(text,), daemon=True).start()

    # ------------------------------------------------------------------
    # Fish Speech (primary)
    # ------------------------------------------------------------------

    def _try_fish_speech(self, text: str) -> bool:
        """Call local Fish Speech container. Returns True on success."""
        try:
            import requests as req

            payload = {
                "text": text,
                "format": "wav",
                "reference_id": _FISH_VOICE_ID,
                "use_memory_cache": "on",
                "normalize": True,
            }

            resp = req.post(
                "{}/v1/tts".format(_FISH_URL),
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=_FISH_TIMEOUT,
            )

            if resp.status_code != 200:
                if self._fish_ok is None:
                    print("[TTS] Fish Speech not available ({}), using fallback."
                          .format(resp.status_code))
                self._fish_ok = False
                return False

            self._fish_ok = True
            self._play_wav_bytes(resp.content)
            return True

        except Exception as exc:
            if self._fish_ok is None or self._fish_ok:
                print("[TTS] Fish Speech unavailable: {}".format(exc))
            self._fish_ok = False
            return False

    # ------------------------------------------------------------------
    # ElevenLabs (secondary)
    # ------------------------------------------------------------------

    def _try_elevenlabs(self, text: str) -> bool:
        """Call ElevenLabs API. Returns True on success."""
        if not (self._el_key and self._el_voice):
            return False
        try:
            from elevenlabs.client import ElevenLabs
            client    = ElevenLabs(api_key=self._el_key)
            audio_gen = client.text_to_speech.convert(
                voice_id=self._el_voice,
                text=text,
                output_format="pcm_22050",
                model_id="eleven_turbo_v2_5",
            )
            pcm   = b"".join(audio_gen)
            audio = np.frombuffer(pcm, dtype=np.int16)
            sd.play(audio, samplerate=22050)
            sd.wait()
            return True
        except Exception as exc:
            print("[TTS] ElevenLabs error: {}".format(exc))
            return False

    # ------------------------------------------------------------------
    # pyttsx3 (last resort)
    # ------------------------------------------------------------------

    def _pyttsx3_speak(self, text: str):
        done = threading.Event()
        self._q.put((text, done))
        done.wait()

    def _pyttsx3_run(self):
        """Single thread that owns the pyttsx3 engine."""
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty('rate', 165)
        engine.setProperty('volume', 1.0)
        voices = engine.getProperty('voices')
        for name in ["guy", "mark", "david", "james"]:
            for v in voices:
                if name in v.name.lower():
                    engine.setProperty('voice', v.id)
                    break
        while True:
            item = self._q.get()
            if item is None:
                break
            text, done_event = item
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception as exc:
                print("[TTS] pyttsx3 error: {}".format(exc))
            if done_event is not None:
                done_event.set()

    # ------------------------------------------------------------------
    # Audio playback helpers
    # ------------------------------------------------------------------

    def _play_wav_bytes(self, wav_bytes: bytes):
        """Decode WAV bytes and play via sounddevice (uses scipy, already installed)."""
        from scipy.io import wavfile
        rate, data = wavfile.read(io.BytesIO(wav_bytes))
        # Normalise to float32 for sounddevice
        if data.dtype == np.int16:
            audio = data.astype(np.float32) / 32768.0
        elif data.dtype == np.int32:
            audio = data.astype(np.float32) / 2147483648.0
        else:
            audio = data.astype(np.float32)
        sd.play(audio, samplerate=rate)
        sd.wait()

    # ------------------------------------------------------------------
    # Startup info
    # ------------------------------------------------------------------

    def _log_config(self):
        fish = _FISH_URL
        el   = "SET" if (self._el_key and self._el_voice) else "NOT SET"
        print("[TTS] Fish Speech : {} (primary — run docker compose to start)".format(fish))
        print("[TTS] ElevenLabs  : {} (secondary fallback)".format(el))
        print("[TTS] pyttsx3     : always available (last resort)")
