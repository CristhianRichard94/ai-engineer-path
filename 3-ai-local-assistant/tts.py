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
import time

import numpy as np
import sounddevice as sd

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis"))
from state import write_state, append_transcript


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
        append_transcript("assistant", text)

        # ponytail: once Fish Speech is known dead this session, don't
        # reattempt the network call every turn - it just adds latency to
        # every reply for a backend that isn't coming back without a restart.
        if self._fish_ok is not False and self._try_fish_speech(text):
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
            self._play_wav_bytes(resp.content, text)
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
            audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
            self._play_and_report_amplitude(audio, 22050, text)
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
        import tempfile

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
                # ponytail: engine.say()+runAndWait() plays through SAPI5's
                # own device selection, which can silently differ from the
                # sounddevice default output (e.g. picks internal speakers
                # while a Bluetooth headset is the actual default) - render
                # to a temp WAV and play it through sounddevice instead, so
                # it always uses the same output device as every other TTS
                # backend in this file.
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    tmp_path = f.name
                engine.save_to_file(text, tmp_path)
                engine.runAndWait()
                self._play_wav_bytes(open(tmp_path, "rb").read(), text)
                os.remove(tmp_path)
            except Exception as exc:
                print("[TTS] pyttsx3 error: {}".format(exc))
            if done_event is not None:
                done_event.set()

    # ------------------------------------------------------------------
    # Audio playback helpers
    # ------------------------------------------------------------------

    def _play_wav_bytes(self, wav_bytes: bytes, text: str = ""):
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
        self._play_and_report_amplitude(audio, rate, text)

    def _play_and_report_amplitude(self, audio: np.ndarray, rate: int, text: str):
        """Play `audio` (float32, mono or multi-channel, already normalised
        to roughly [-1, 1]) via sounddevice, while periodically writing the
        current RMS amplitude of the audio under the playhead to state.json
        so the control UI can drive an audio-reactive orb. Non-blocking
        `sd.play()` + a polling loop, then `sd.wait()` to fully drain.
        """
        # Collapse to mono for amplitude purposes if multi-channel.
        mono = audio if audio.ndim == 1 else audio.mean(axis=1)
        total_samples = len(mono)
        window = max(1, int(rate * 0.05))  # ~50ms RMS window
        poll_interval = 1 / 15  # ~15Hz amplitude updates

        sd.play(audio, samplerate=rate)
        start = time.monotonic()
        try:
            while True:
                stream = sd.get_stream()
                active = stream is not None and stream.active
                elapsed = time.monotonic() - start
                if not active or elapsed * rate >= total_samples:
                    break

                idx = int(elapsed * rate)
                window_slice = mono[idx:idx + window]
                if len(window_slice) > 0:
                    rms = float(np.sqrt(np.mean(np.square(window_slice))))
                    rms = rms if np.isfinite(rms) else 0.0
                    amplitude = max(0.0, min(1.0, rms))
                    write_state("speaking", detail=text, amplitude=amplitude)

                time.sleep(poll_interval)
            sd.wait()
        except Exception:
            # Playback failed mid-stream (device disconnect, driver error,
            # etc.) - do not leave state.json frozen at "speaking" with a
            # stale amplitude. Move off "speaking" before propagating the
            # error so callers' fallback chain / error handling still runs.
            write_state("error", detail="TTS playback failed")
            raise
        else:
            # Playback finished normally - drop the amplitude key so the
            # SSE payload cleanly reflects "no longer actively playing"
            # instead of lingering at the last polled value.
            write_state("speaking", detail=text)

    # ------------------------------------------------------------------
    # Startup info
    # ------------------------------------------------------------------

    def _log_config(self):
        fish = _FISH_URL
        el   = "SET" if (self._el_key and self._el_voice) else "NOT SET"
        print("[TTS] Fish Speech : {} (primary — run docker compose to start)".format(fish))
        print("[TTS] ElevenLabs  : {} (secondary fallback)".format(el))
        print("[TTS] pyttsx3     : always available (last resort)")
