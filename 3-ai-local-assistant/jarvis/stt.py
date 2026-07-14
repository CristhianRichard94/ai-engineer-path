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
        # ponytail: sd.rec()/sd.wait() is blocking-mode API, unsupported on
        # WDM-KS-only input devices (common on Windows) - use InputStream
        # callback instead, same fix as wake_word.py.
        print("[JARVIS] Listening...")
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
            return text if text else None
        except Exception as e:
            print(f"[STT] Error: {e}")
            return None