# wake_word.py - captures at the default mic's native rate, resampled to 16000 for the model
import os
import math
import urllib.request
import sounddevice as sd
import numpy as np
from scipy.signal import resample_poly
from openwakeword.model import Model
from state import write_state
from audio_input import find_input_device, NoMicrophoneError  # noqa: F401 - re-exported for main.py


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
        self.device, self.capture_rate = find_input_device()
        self.chunk = int(0.08 * self.capture_rate)  # ~80ms per block

        g = math.gcd(self.model_rate, int(self.capture_rate))
        self._resample_up   = self.model_rate // g
        self._resample_down = int(self.capture_rate) // g

    def _resample(self, audio):
        if self._resample_up == self._resample_down:
            return audio.astype(np.int16)
        return resample_poly(audio, up=self._resample_up, down=self._resample_down).astype(np.int16)

    def listen_for_wake(self):
        # ponytail: blocking-mode streams (stream.read()) aren't supported on
        # WDM-KS-only input devices (common on Windows). Callback + queue works
        # on every host API, so it's the portable default here.
        import queue

        print("[JARVIS] Waiting for wake word...")
        write_state("wake_listening")

        _WAKE_QUEUE_TIMEOUT_S = 10.0

        # Outer loop: lets us actually reopen sd.InputStream on a new device
        # when the currently open one stops producing audio (e.g. a
        # Bluetooth reconnect that changes the device index/samplerate).
        while True:
            q = queue.Queue()

            def _callback(indata, frames, time_info, status):
                q.put(indata.copy())

            received_any_chunk = False
            warned_this_stall = False
            reopen_with_new_device = False

            with sd.InputStream(
                samplerate=self.capture_rate,
                channels=1,
                dtype='int16',
                blocksize=self.chunk,
                device=self.device,
                callback=_callback,
            ):
                while True:
                    try:
                        raw = q.get(timeout=_WAKE_QUEUE_TIMEOUT_S)
                    except queue.Empty:
                        if not received_any_chunk and not warned_this_stall:
                            # Only warn/retry once per stall episode - avoid
                            # spamming logs and rescanning every 10s forever
                            # on a genuinely dead mic.
                            warned_this_stall = True
                            print("[WAKE] No audio from input device — check microphone.")
                            new_device, new_rate = find_input_device()
                            if new_device != self.device or new_rate != self.capture_rate:
                                self.device = new_device
                                self.capture_rate = new_rate
                                self.chunk = int(0.08 * self.capture_rate)
                                g = math.gcd(self.model_rate, int(self.capture_rate))
                                self._resample_up = self.model_rate // g
                                self._resample_down = int(self.capture_rate) // g
                                reopen_with_new_device = True
                                break
                        continue

                    received_any_chunk = True
                    warned_this_stall = False
                    audio_16k = self._resample(raw.flatten())
                    self.model.predict(audio_16k)
                    scores = self.model.prediction_buffer.get("hey_jarvis", [0])
                    if max(scores) >= self.threshold:
                        self.model.prediction_buffer.clear()
                        return True

            # Stream was closed because the resolved device changed - loop
            # back around and reopen sd.InputStream on the new device.
            if reopen_with_new_device:
                continue

    def cleanup(self):
        pass
