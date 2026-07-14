"""
test/stt.py — Unit tests for SpeechTranscriber.

sounddevice and the OpenAI client are mocked so tests run without a mic
or network access.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

for mod in ("sounddevice", "openai"):
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

import stt as stt_module
from stt import SpeechTranscriber


def _make_transcriber(devices):
    with patch("stt.openai"), patch("stt.sd") as mock_sd:
        mock_sd.query_devices.return_value = devices
        mock_sd.default.device = (7, 7)
        t = SpeechTranscriber(api_key="test-key")
    return t


class TestFindMic(unittest.TestCase):

    def test_prefers_realtek_input_device(self):
        devices = [
            {"name": "USB Mic", "max_input_channels": 1},
            {"name": "Realtek Mic Array", "max_input_channels": 2},
        ]
        t = _make_transcriber(devices)
        self.assertEqual(t.device, 1)

    def test_falls_back_to_default_when_no_realtek_input(self):
        devices = [{"name": "USB Mic", "max_input_channels": 1}]
        t = _make_transcriber(devices)
        self.assertEqual(t.device, 7)


class TestResample(unittest.TestCase):

    def test_resample_downsamples_48k_to_16k_length(self):
        t = _make_transcriber([{"name": "x", "max_input_channels": 1}])
        import numpy as np
        audio = np.zeros(48000, dtype=np.int16)
        out = t._resample(audio)
        self.assertEqual(len(out), 16000)
        self.assertEqual(out.dtype, np.int16)


def _mock_input_stream(mock_sd, chunk):
    """Make sd.InputStream(...) a context manager that fires callback once with `chunk`."""
    stream = MagicMock()
    stream.__enter__ = MagicMock(return_value=stream)
    stream.__exit__ = MagicMock(return_value=False)

    def _ctor(*args, **kwargs):
        callback = kwargs.get("callback")
        if callback is not None:
            callback(chunk, len(chunk), None, None)
        return stream

    mock_sd.InputStream.side_effect = _ctor
    mock_sd.sleep = MagicMock()


class TestCaptureAndTranscribe(unittest.TestCase):

    def test_uses_detected_device_not_hardcoded(self):
        t = _make_transcriber([{"name": "Realtek Mic", "max_input_channels": 1}])
        import numpy as np

        with patch("stt.sd") as mock_sd:
            _mock_input_stream(mock_sd, np.zeros((100, 1), dtype=np.int16))
            t.client.audio.transcriptions.create.return_value = MagicMock(text="hello")
            t.capture_and_transcribe()
            _, kwargs = mock_sd.InputStream.call_args
            self.assertEqual(kwargs["device"], t.device)

    def test_returns_none_on_api_exception(self):
        t = _make_transcriber([{"name": "x", "max_input_channels": 1}])
        import numpy as np
        with patch("stt.sd") as mock_sd:
            _mock_input_stream(mock_sd, np.zeros((100, 1), dtype=np.int16))
            t.client.audio.transcriptions.create.side_effect = Exception("api down")
            result = t.capture_and_transcribe()
            self.assertIsNone(result)

    def test_returns_none_on_empty_transcript(self):
        t = _make_transcriber([{"name": "x", "max_input_channels": 1}])
        import numpy as np
        with patch("stt.sd") as mock_sd:
            _mock_input_stream(mock_sd, np.zeros((100, 1), dtype=np.int16))
            t.client.audio.transcriptions.create.return_value = MagicMock(text="   ")
            result = t.capture_and_transcribe()
            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
