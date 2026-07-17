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

import numpy as np

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
        audio = np.zeros(48000, dtype=np.int16)
        out = t._resample(audio)
        self.assertEqual(len(out), 16000)
        self.assertEqual(out.dtype, np.int16)

    def test_no_resample_when_device_already_native_16k(self):
        t = _make_transcriber(default_index=18, device_info={
            "name": "x", "default_samplerate": 16000.0
        })
        audio = np.zeros(16000, dtype=np.int16)
        out = t._resample(audio)
        self.assertEqual(len(out), 16000)


# 4800 frames @ 48000Hz = 0.1s per chunk — long enough that a single chunk
# can trip the hard `max_seconds` cap in tests without any real-time waits.
_CHUNK_FRAMES = 4800
_SPEECH_CHUNK = np.full((_CHUNK_FRAMES, 1), 5000, dtype=np.int16)   # RMS >> threshold
_SILENCE_CHUNK = np.zeros((_CHUNK_FRAMES, 1), dtype=np.int16)       # RMS 0


def _mock_input_stream(mock_sd, chunks):
    """Make sd.InputStream(...) a context manager whose callback fires once
    per entry in `chunks`, in order, synchronously at construction time —
    mirroring how a real InputStream would deliver a sequence of blocks."""
    stream = MagicMock()
    stream.__enter__ = MagicMock(return_value=stream)
    stream.__exit__ = MagicMock(return_value=False)

    def _ctor(*args, **kwargs):
        callback = kwargs.get("callback")
        if callback is not None:
            for chunk in chunks:
                callback(chunk, len(chunk), None, None)
        return stream

    mock_sd.InputStream.side_effect = _ctor
    mock_sd.sleep = MagicMock()
    mock_sd.play = MagicMock()
    mock_sd.wait = MagicMock()
    return stream


def _mock_input_stream_with_call_order(mock_sd, chunks):
    """Like _mock_input_stream, but also records the order in which
    sd.play, sd.wait, and sd.InputStream(...) are invoked, so tests can
    assert the listen-cue fully finishes (play -> wait) before capture
    starts (InputStream construction)."""
    call_order = []

    stream = MagicMock()
    stream.__enter__ = MagicMock(return_value=stream)
    stream.__exit__ = MagicMock(return_value=False)

    def _ctor(*args, **kwargs):
        call_order.append("InputStream")
        callback = kwargs.get("callback")
        if callback is not None:
            for chunk in chunks:
                callback(chunk, len(chunk), None, None)
        return stream

    def _play(*args, **kwargs):
        call_order.append("play")

    def _wait(*args, **kwargs):
        call_order.append("wait")

    mock_sd.InputStream.side_effect = _ctor
    mock_sd.sleep = MagicMock()
    mock_sd.play = MagicMock(side_effect=_play)
    mock_sd.wait = MagicMock(side_effect=_wait)
    return stream, call_order


class TestCaptureAndTranscribe(unittest.TestCase):

    def test_uses_detected_device_not_hardcoded(self):
        t = _make_transcriber()
        with patch("stt.sd") as mock_sd:
            _mock_input_stream(mock_sd, [_SPEECH_CHUNK])
            t.client.audio.transcriptions.create.return_value = MagicMock(text="hello")
            # Hard cap trips after the single (loud) chunk since 0.1s of
            # captured audio already exceeds it — avoids waiting out the
            # post-speech silence window in this test.
            t.capture_and_transcribe(max_seconds=0.05)
            _, kwargs = mock_sd.InputStream.call_args
            self.assertEqual(kwargs["device"], t.device)

    def test_returns_none_on_api_exception(self):
        t = _make_transcriber()
        with patch("stt.sd") as mock_sd:
            _mock_input_stream(mock_sd, [_SPEECH_CHUNK])
            t.client.audio.transcriptions.create.side_effect = Exception("api down")
            result = t.capture_and_transcribe(max_seconds=0.05)
            self.assertIsNone(result)

    def test_returns_none_on_empty_transcript(self):
        t = _make_transcriber()
        with patch("stt.sd") as mock_sd:
            _mock_input_stream(mock_sd, [_SPEECH_CHUNK])
            t.client.audio.transcriptions.create.return_value = MagicMock(text="   ")
            result = t.capture_and_transcribe(max_seconds=0.05)
            self.assertIsNone(result)

    def test_silence_before_speech_times_out_and_returns_none_without_api_call(self):
        """If nothing crosses the speech threshold within the pre-speech
        timeout window, give up and return None - matching main.py's
        existing `if not command:` fallback contract - without ever
        calling the transcription API."""
        t = _make_transcriber()
        with patch("stt.sd") as mock_sd, \
             patch.object(stt_module, "_PRE_SPEECH_TIMEOUT_S", 0.05):
            _mock_input_stream(mock_sd, [_SILENCE_CHUNK])
            result = t.capture_and_transcribe()
            self.assertIsNone(result)
            t.client.audio.transcriptions.create.assert_not_called()

    def test_speech_then_silence_stops_early_not_at_hard_cap(self):
        """Once speech starts, a contiguous run of silence should stop the
        capture well before the (much larger) hard cap - not wait it out."""
        t = _make_transcriber()
        with patch("stt.sd") as mock_sd, \
             patch.object(stt_module, "_POST_SPEECH_SILENCE_S", 0.15):
            # 1 speech chunk (0.1s) + 2 silence chunks (0.1s each = 0.2s of
            # contiguous silence, past the 0.15s patched threshold) should
            # end the capture — well short of the 15s default hard cap.
            _mock_input_stream(mock_sd, [_SPEECH_CHUNK, _SILENCE_CHUNK, _SILENCE_CHUNK])
            t.client.audio.transcriptions.create.return_value = MagicMock(text="hi")
            result = t.capture_and_transcribe()
            self.assertEqual(result, "hi")
            t.client.audio.transcriptions.create.assert_called_once()

    def test_listen_cue_beep_plays_on_listen_start(self):
        t = _make_transcriber()
        with patch("stt.sd") as mock_sd:
            _mock_input_stream(mock_sd, [_SPEECH_CHUNK])
            t.client.audio.transcriptions.create.return_value = MagicMock(text="hi")
            t.capture_and_transcribe(max_seconds=0.05)
            mock_sd.play.assert_called_once()

    def test_listen_cue_fully_finishes_before_capture_starts(self):
        """Regression: sd.play() is non-blocking, so without an explicit
        sd.wait() the beep's tail can bleed into the mic and get picked up
        by the VAD as speech. Assert the ordering is play -> wait ->
        InputStream, i.e. the cue is fully drained before capture opens."""
        t = _make_transcriber()
        with patch("stt.sd") as mock_sd:
            _stream, call_order = _mock_input_stream_with_call_order(mock_sd, [_SPEECH_CHUNK])
            t.client.audio.transcriptions.create.return_value = MagicMock(text="hi")
            t.capture_and_transcribe(max_seconds=0.05)

            self.assertIn("play", call_order)
            self.assertIn("wait", call_order)
            self.assertIn("InputStream", call_order)
            play_idx = call_order.index("play")
            wait_idx = call_order.index("wait")
            stream_idx = call_order.index("InputStream")
            self.assertLess(play_idx, wait_idx)
            self.assertLess(wait_idx, stream_idx)


if __name__ == "__main__":
    unittest.main()
