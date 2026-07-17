# stt.py — captures at the default mic's native rate, resampled to 16000 for Whisper
import math
import openai
import sounddevice as sd
import numpy as np
from scipy.signal import resample_poly
import io, wave
from state import write_state, append_transcript

class SpeechTranscriber:
    def __init__(self, api_key: str):
        self.client     = openai.OpenAI(api_key=api_key)
        self.model_rate = 16000
        self.device, self.capture_rate = self._find_mic()

        g = math.gcd(self.model_rate, int(self.capture_rate))
        self._resample_up   = self.model_rate // g
        self._resample_down = int(self.capture_rate) // g

    def _find_mic(self):
        # ponytail: trust the OS default input device rather than guessing by
        # name — see wake_word.py._find_mic for why.
        index = sd.default.device[0]
        info  = sd.query_devices(index)
        return index, info['default_samplerate']

    def _resample(self, audio: np.ndarray) -> np.ndarray:
        if self._resample_up == self._resample_down:
            return audio.astype(np.int16)
        return resample_poly(audio, up=self._resample_up, down=self._resample_down).astype(np.int16)

    def capture_and_transcribe(self, max_seconds=8) -> str | None:
        # ponytail: sd.rec()/sd.wait() is blocking-mode API, unsupported on
        # WDM-KS-only input devices (common on Windows) - use InputStream
        # callback instead, same fix as wake_word.py.
        print("[JARVIS] Listening...")
        write_state("listening")
        frames = []
        with sd.InputStream(
            samplerate=self.capture_rate,
            channels=1,
            dtype='int16',
            device=self.device,
            callback=lambda indata, n, t, status: frames.append(indata.copy()),
        ):
            sd.sleep(int(max_seconds * 1000))

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