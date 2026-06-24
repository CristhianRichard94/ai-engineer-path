# stt.py — 48000 Hz capture, resampled to 16000 for Whisper
import openai
import sounddevice as sd
import numpy as np
from scipy.signal import resample_poly
import io, wave

class SpeechTranscriber:
    def __init__(self, api_key: str):
        self.client       = openai.OpenAI(api_key=api_key)
        self.capture_rate = 48000
        self.model_rate   = 16000
        self.device       = self._find_mic()

    def _find_mic(self):
        for i, d in enumerate(sd.query_devices()):
            if d['max_input_channels'] > 0 and 'Realtek' in d['name']:
                return i
        return sd.default.device[0]

    def _resample(self, audio: np.ndarray) -> np.ndarray:
        return resample_poly(audio, up=1, down=3).astype(np.int16)

    def capture_and_transcribe(self, max_seconds=8) -> str | None:
        print("[JARVIS] Listening...")
        raw = sd.rec(
            int(max_seconds * self.capture_rate),
            samplerate=self.capture_rate,
            channels=1,
            dtype='int16',
            device=15
        )
        sd.wait()
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
            return text if text else None
        except Exception as e:
            print(f"[STT] Error: {e}")
            return None