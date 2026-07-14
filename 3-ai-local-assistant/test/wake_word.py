"""
test/wake_word.py — Unit tests for WakeWordDetector.

sounddevice, openwakeword, and the model-download step are all mocked so
tests run without a mic, ONNX models, or network access.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

for mod in ("sounddevice", "openwakeword", "openwakeword.model"):
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

import wake_word as ww_module
from wake_word import WakeWordDetector


def _make_detector(default_index, device_info):
    with patch("wake_word._ensure_models"), \
         patch("wake_word.Model"), \
         patch("wake_word.sd") as mock_sd:
        mock_sd.default.device = (default_index, default_index)
        mock_sd.query_devices.return_value = device_info
        detector = WakeWordDetector()
    return detector


class TestFindMic(unittest.TestCase):

    def test_uses_os_default_input_device_not_name_matching(self):
        # Regression: previously a "prefer Realtek" name match could pick a
        # disconnected device over the mic the OS actually has active
        # (e.g. a connected Bluetooth headset that isn't named Realtek).
        detector = _make_detector(18, {
            "name": "Auriculares con microfono (Bluetooth)",
            "default_samplerate": 16000.0,
        })
        self.assertEqual(detector.device, 18)
        self.assertEqual(detector.capture_rate, 16000.0)

    def test_capture_rate_taken_from_device_info(self):
        detector = _make_detector(11, {
            "name": "Realtek Mic Array",
            "default_samplerate": 48000.0,
        })
        self.assertEqual(detector.capture_rate, 48000.0)


class TestResample(unittest.TestCase):

    def test_resample_downsamples_48k_to_16k_length(self):
        detector = _make_detector(11, {"name": "x", "default_samplerate": 48000.0})
        import numpy as np
        audio = np.zeros(3840, dtype=np.int16)
        out = detector._resample(audio)
        self.assertEqual(len(out), 1280)
        self.assertEqual(out.dtype, np.int16)

    def test_no_resample_when_device_already_native_16k(self):
        detector = _make_detector(18, {"name": "x", "default_samplerate": 16000.0})
        import numpy as np
        audio = np.zeros(1280, dtype=np.int16)
        out = detector._resample(audio)
        self.assertEqual(len(out), 1280)


class TestListenForWake(unittest.TestCase):

    def test_returns_true_once_score_crosses_threshold(self):
        detector = _make_detector(11, {"name": "x", "default_samplerate": 48000.0})
        detector.threshold = 0.3

        import numpy as np
        chunk = np.zeros((detector.chunk, 1), dtype=np.int16)

        mock_stream = MagicMock()
        mock_stream.__enter__.return_value = mock_stream

        detector.model.prediction_buffer = {"hey_jarvis": [0.9]}

        def _ctor(*args, **kwargs):
            callback = kwargs.get("callback")
            callback(chunk, len(chunk), None, None)
            return mock_stream

        with patch("wake_word.sd") as mock_sd:
            mock_sd.InputStream.side_effect = _ctor
            result = detector.listen_for_wake()

        self.assertTrue(result)
        detector.model.predict.assert_called()


if __name__ == "__main__":
    unittest.main()
