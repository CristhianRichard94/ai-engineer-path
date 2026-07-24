# stt.py — captures at the default mic's native rate, resampled to 16000 for Whisper
import math
import queue
import openai
import sounddevice as sd
import numpy as np
from scipy.signal import resample_poly
import io, wave
from state import write_state, append_transcript
from audio_input import find_input_device

# ── VAD (voice activity detection) tuning ───────────────────────────────────
# ponytail: plain RMS-over-chunk energy thresholding on int16 PCM, no
# adaptive/ambient-noise calibration. Fixed threshold - may need retuning per
# mic (too sensitive: cuts off in loud rooms; too insensitive: never detects
# quiet speech). Upgrade path if this proves unreliable in practice: sample a
# short ambient-noise window at start of each turn and set the threshold
# relative to that, instead of this fixed constant.
_SPEECH_RMS_THRESHOLD = 300     # int16 RMS level above which a chunk counts as speech
_PRE_SPEECH_TIMEOUT_S = 4.0     # give up if no speech starts within this long
_POST_SPEECH_SILENCE_S = 1.0    # stop this long after speech trails off into silence
_CHUNK_S = 0.08                 # ~80ms per capture chunk, same as wake_word.py

# ── Listening-cue tone ───────────────────────────────────────────────────────
_BEEP_FREQ_HZ = 880
_BEEP_DURATION_S = 0.15
_BEEP_AMPLITUDE = 0.15          # kept quiet/short - a cue, not an alert


def _make_beep(rate: int) -> np.ndarray:
    """Synthesize a short, quiet sine-tone 'you can talk now' cue."""
    n = int(rate * _BEEP_DURATION_S)
    t = np.linspace(0, _BEEP_DURATION_S, n, endpoint=False)
    # Short fade in/out so the tone doesn't click at the edges.
    fade = np.minimum(1.0, np.minimum(t, _BEEP_DURATION_S - t) / 0.02 + 0.01)
    tone = _BEEP_AMPLITUDE * np.sin(2 * np.pi * _BEEP_FREQ_HZ * t) * fade
    return tone.astype(np.float32)


class SpeechTranscriber:
    def __init__(self, api_key: str):
        self.client     = openai.OpenAI(api_key=api_key)
        self.model_rate = 16000
        self.device, self.capture_rate = find_input_device()

        g = math.gcd(self.model_rate, int(self.capture_rate))
        self._resample_up   = self.model_rate // g
        self._resample_down = int(self.capture_rate) // g

    def _resample(self, audio: np.ndarray) -> np.ndarray:
        if self._resample_up == self._resample_down:
            return audio.astype(np.int16)
        return resample_poly(audio, up=self._resample_up, down=self._resample_down).astype(np.int16)

    def _play_listen_cue(self):
        """Best-effort audible 'you can talk now' cue - never block/crash the
        listen flow if playback fails (e.g. no output device).

        Blocks on sd.wait() until playback finishes (~150ms) so the beep's
        tail can't bleed into the mic capture that starts right after this
        returns - otherwise the beep gets picked up as speech by the VAD
        (see stt regression test for details)."""
        try:
            sd.play(_make_beep(self.model_rate), samplerate=self.model_rate)
            sd.wait()
        except Exception as e:
            print(f"[STT] Listen cue failed: {e}")

    def capture_and_transcribe(self, max_seconds=15) -> str | None:
        # ponytail: sd.rec()/sd.wait() is blocking-mode API, unsupported on
        # WDM-KS-only input devices (common on Windows) - use InputStream
        # callback instead, same fix as wake_word.py. Silence-based auto-stop
        # (VAD) replaces the old fixed-duration blind capture: we stop as
        # soon as the user finishes speaking instead of always waiting out
        # the full window, and give up early if nothing is said at all.
        print("[JARVIS] Listening...")
        write_state("listening")
        self._play_listen_cue()

        chunk_frames = max(1, int(_CHUNK_S * self.capture_rate))
        q = queue.Queue()

        def _callback(indata, n, t, status):
            q.put(indata.copy())

        frames = []
        speech_started = False
        silence_run_s = 0.0
        captured_s = 0.0
        gave_up = False

        with sd.InputStream(
            samplerate=self.capture_rate,
            channels=1,
            dtype='int16',
            blocksize=chunk_frames,
            device=self.device,
            callback=_callback,
        ):
            while True:
                try:
                    # Real fallback timeout in case the stream stalls; the
                    # duration-based checks below are what normally end the
                    # loop (based on captured audio time, not wall clock, so
                    # tests can drive this deterministically).
                    chunk = q.get(timeout=_PRE_SPEECH_TIMEOUT_S)
                except queue.Empty:
                    gave_up = not speech_started
                    break

                frames.append(chunk)
                chunk_s = len(chunk) / float(self.capture_rate)
                captured_s += chunk_s

                rms = float(np.sqrt(np.mean(np.square(chunk.astype(np.float64)))))
                is_speech = rms >= _SPEECH_RMS_THRESHOLD

                if not speech_started:
                    if is_speech:
                        speech_started = True
                        silence_run_s = 0.0
                    elif captured_s >= _PRE_SPEECH_TIMEOUT_S:
                        gave_up = True
                        break
                else:
                    if is_speech:
                        silence_run_s = 0.0
                    else:
                        silence_run_s += chunk_s
                        if silence_run_s >= _POST_SPEECH_SILENCE_S:
                            break

                if captured_s >= max_seconds:
                    break

        if gave_up or not speech_started:
            print("[STT] No speech detected.")
            return None

        raw = np.concatenate(frames, axis=0) if frames else np.zeros((0, 1), dtype='int16')
        audio_16k = self._resample(raw.flatten())

        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.model_rate)
            wf.writeframes(audio_16k.tobytes())
        buf.seek(0)
        buf.name = "audio.wav"

        try:
            result = self.client.audio.transcriptions.create(
                model="whisper-1",
                file=buf,
                language="en"
            )
            text = result.text.strip()
            print(f"[STT] Heard: {text}")
            if text:
                write_state("thinking", detail=text)
                append_transcript("user", text)
            return text if text else None
        except Exception as e:
            print(f"[STT] Error: {e}")
            return None