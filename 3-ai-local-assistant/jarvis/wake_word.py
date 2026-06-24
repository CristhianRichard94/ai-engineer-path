# wake_word.py - 48000 Hz capture, resampled to 16000 for the model
import os
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
        self.capture_rate = 48000   # what Realtek accepts
        self.model_rate   = 16000   # what OpenWakeWord expects
        self.chunk        = 3840    # 80ms at 48000 Hz (= 1280 at 16000)
        self.threshold    = 0.3
        self.device       = self._find_mic()

    def _find_mic(self):
        for i, d in enumerate(sd.query_devices()):
            if d['max_input_channels'] > 0 and 'Realtek' in d['name']:
                print("[MIC] Using -> index {}: {}".format(i, d['name']))
                return i
        return sd.default.device[0]

    def _resample(self, audio):
        # downsample 48000 -> 16000 (factor 1/3)
        return resample_poly(audio, up=1, down=3).astype(np.int16)

    def listen_for_wake(self):
        print("[JARVIS] Waiting for wake word...")
        with sd.InputStream(
            samplerate=self.capture_rate,
            channels=1,
            dtype='int16',
            blocksize=self.chunk,
            device=self.device,
        ) as stream:
            while True:
                raw, _ = stream.read(self.chunk)
                audio_16k = self._resample(raw.flatten())
                self.model.predict(audio_16k)
                scores = self.model.prediction_buffer.get("hey_jarvis", [0])
                if max(scores) >= self.threshold:
                    self.model.prediction_buffer.clear()
                    return True

    def cleanup(self):
        pass
