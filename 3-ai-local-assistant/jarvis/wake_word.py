# wake_word.py - captures at the default mic's native rate, resampled to 16000 for the model
import os
import math
import urllib.request
import sounddevice as sd
import numpy as np
from scipy.signal import resample_poly
from openwakeword.model import Model

# ── Model download ──────────────────────────────────────────────────────
_BASE_URL = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1"
_MODELS = {
    "hey_jarvis_v0.1.onnx": "{}/hey_jarvis_v0.1.onnx".format(_BASE_URL),
    "melspectrogram.onnx" : "{}/melspectrogram.onnx".format(_BASE_URL),
    "embedding_model.onnx": "{}/embedding_model.onnx".format(_BASE_URL),
}

def _ensure_models():
    """Download any missing ONNX model files into the openwakeword resources dir."""
    import openwakeword
    models_dir = os.path.join(
        os.path.dirname(os.path.abspath(openwakeword.__file__)),
        "resources", "models"
    )
    os.makedirs(models_dir, exist_ok=True)

    for filename, url in _MODELS.items():
        dest = os.path.join(models_dir, filename)
        if not os.path.exists(dest):
            print("[WAKE] Downloading {} ...".format(filename))
            try:
                urllib.request.urlretrieve(url, dest)
                print("[WAKE] Downloaded {} ({:.1f} KB)".format(
                    filename, os.path.getsize(dest) / 1024))
            except Exception as e:
                print("[WAKE] Failed to download {}: {}".format(filename, e))
                raise

    return models_dir


class WakeWordDetector:
    def __init__(self):
        _ensure_models()

        self.model = Model(
            wakeword_models=["hey_jarvis"],
            inference_framework="onnx"
        )
        self.model_rate   = 16000   # what OpenWakeWord expects
        self.threshold    = 0.3
        self.device, self.capture_rate = self._find_mic()
        self.chunk = int(0.08 * self.capture_rate)  # ~80ms per block

        g = math.gcd(self.model_rate, int(self.capture_rate))
        self._resample_up   = self.model_rate // g
        self._resample_down = int(self.capture_rate) // g

    def _find_mic(self):
        # ponytail: trust the OS default input device rather than guessing by
        # name — a hardcoded "prefer Realtek" match can pick an unplugged/
        # disconnected device over the mic that's actually active (e.g. a
        # connected Bluetooth headset).
        index = sd.default.device[0]
        info  = sd.query_devices(index)
        print("[MIC] Using -> index {}: {} ({} Hz)".format(
            index, info['name'], info['default_samplerate']))
        return index, info['default_samplerate']

    def _resample(self, audio):
        if self._resample_up == self._resample_down:
            return audio.astype(np.int16)
        return resample_poly(audio, up=self._resample_up, down=self._resample_down).astype(np.int16)

    def listen_for_wake(self):
        # ponytail: blocking-mode streams (stream.read()) aren't supported on
        # WDM-KS-only input devices (common on Windows). Callback + queue works
        # on every host API, so it's the portable default here.
        import queue
        q = queue.Queue()

        def _callback(indata, frames, time_info, status):
            q.put(indata.copy())

        print("[JARVIS] Waiting for wake word...")
        with sd.InputStream(
            samplerate=self.capture_rate,
            channels=1,
            dtype='int16',
            blocksize=self.chunk,
            device=self.device,
            callback=_callback,
        ):
            while True:
                raw = q.get()
                audio_16k = self._resample(raw.flatten())
                self.model.predict(audio_16k)
                scores = self.model.prediction_buffer.get("hey_jarvis", [0])
                if max(scores) >= self.threshold:
                    self.model.prediction_buffer.clear()
                    return True

    def cleanup(self):
        pass
