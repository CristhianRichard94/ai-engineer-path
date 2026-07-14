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


def _make_detector(devices):
    with patch("wake_word._ensure_models"), \
         patch("wake_word.Model"), \
         patch("wake_word.sd") as mock_sd:
        mock_sd.query_devices.return_value = devices
        mock_sd.default.device = (7, 7)
        detector = WakeWordDetector()
    return detector


class TestFindMic(unittest.TestCase):

    def test_prefers_realtek_input_device(self):
        devices = [
            {"name": "Microphone (USB)", "max_input_channels": 1},
            {"name": "Speakers (Realtek(R) Audio)", "max_input_channels": 0},
            {"name": "Realtek Mic Array", "max_input_channels": 2},
        ]
        detector = _make_detector(devices)
        self.assertEqual(detector.device, 2)

    def test_falls_back_to_default_when_no_realtek_input(self):
        devices = [
            {"name": "USB Mic", "max_input_channels": 1},
        ]
        detector = _make_detector(devices)
        self.assertEqual(detector.device, 7)


class TestResample(unittest.TestCase):

    def test_resample_downsamples_48k_to_16k_length(self):
        detector = _make_detector([{"name": "x", "max_input_channels": 1}])
        import numpy as np
        audio = np.zeros(3840, dtype=np.int16)
        out = detector._resample(audio)
        self.assertEqual(len(out), 1280)
        self.assertEqual(out.dtype, np.int16)


class TestListenForWake(unittest.TestCase):

    def test_returns_true_once_score_crosses_threshold(self):
        detector = _make_detector([{"name": "x", "max_input_channels": 1}])
        detector.threshold = 0.3

        import numpy as np
        chunk = np.zeros((detector.chunk, 1), dtype=np.int16)

        mock_stream = MagicMock()
        mock_stream.read.return_value = (chunk, None)
        mock_stream.__enter__.return_value = mock_stream

        detector.model.prediction_buffer = {"hey_jarvis": [0.9]}

        with patch("wake_word.sd") as mock_sd:
            mock_sd.InputStream.return_value = mock_stream
            result = detector.listen_for_wake()

        self.assertTrue(result)
        detector.model.predict.assert_called()


if __name__ == "__main__":
    unittest.main()
