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
JARVIS_DIR = os.path.join(ROOT, "jarvis")
if JARVIS_DIR not in sys.path:
    sys.path.insert(0, JARVIS_DIR)

for mod in ("sounddevice", "openai"):
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

import stt as stt_module
from stt import SpeechTranscriber


def _make_transcriber(default_index=7, device_info=None):
    device_info = device_info or {"name": "x", "default_samplerate": 48000.0}
    with patch("stt.openai"), patch("stt.sd") as mock_sd:
        mock_sd.default.device = (default_index, default_index)
        mock_sd.query_devices.return_value = device_info
        t = SpeechTranscriber(api_key="test-key")
    return t


class TestFindMic(unittest.TestCase):

    def test_uses_os_default_input_device_not_name_matching(self):
        # Regression: previously a "prefer Realtek" name match could pick a
        # disconnected device over the mic the OS actually has active.
        t = _make_transcriber(default_index=18, device_info={
            "name": "Auriculares con microfono (Bluetooth)",
            "default_samplerate": 16000.0,
        })
        self.assertEqual(t.device, 18)
        self.assertEqual(t.capture_rate, 16000.0)


class TestResample(unittest.TestCase):

    def test_resample_downsamples_48k_to_16k_length(self):
        t = _make_transcriber(device_info={"name": "x", "default_samplerate": 48000.0})
        import numpy as np
        audio = np.zeros(48000, dtype=np.int16)
        out = t._resample(audio)
        self.assertEqual(len(out), 16000)
        self.assertEqual(out.dtype, np.int16)

    def test_no_resample_when_device_already_native_16k(self):
        t = _make_transcriber(default_index=18, device_info={
            "name": "x", "default_samplerate": 16000.0
        })
        import numpy as np
        audio = np.zeros(16000, dtype=np.int16)
        out = t._resample(audio)
        self.assertEqual(len(out), 16000)


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
        t = _make_transcriber()
        import numpy as np

        with patch("stt.sd") as mock_sd:
            _mock_input_stream(mock_sd, np.zeros((100, 1), dtype=np.int16))
            t.client.audio.transcriptions.create.return_value = MagicMock(text="hello")
            t.capture_and_transcribe()
            _, kwargs = mock_sd.InputStream.call_args
            self.assertEqual(kwargs["device"], t.device)

    def test_returns_none_on_api_exception(self):
        t = _make_transcriber()
        import numpy as np
        with patch("stt.sd") as mock_sd:
            _mock_input_stream(mock_sd, np.zeros((100, 1), dtype=np.int16))
            t.client.audio.transcriptions.create.side_effect = Exception("api down")
            result = t.capture_and_transcribe()
            self.assertIsNone(result)

    def test_returns_none_on_empty_transcript(self):
        t = _make_transcriber()
        import numpy as np
        with patch("stt.sd") as mock_sd:
            _mock_input_stream(mock_sd, np.zeros((100, 1), dtype=np.int16))
            t.client.audio.transcriptions.create.return_value = MagicMock(text="   ")
            result = t.capture_and_transcribe()
            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
