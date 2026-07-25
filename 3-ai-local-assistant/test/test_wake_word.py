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
JARVIS_DIR = os.path.join(ROOT, "jarvis")
if JARVIS_DIR not in sys.path:
    sys.path.insert(0, JARVIS_DIR)

for mod in ("sounddevice", "openwakeword", "openwakeword.model"):
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

import wake_word as ww_module
from wake_word import WakeWordDetector
from audio_input import NoMicrophoneError


def _make_detector(default_index, device_info):
    with patch("wake_word._ensure_models"), \
         patch("wake_word.Model"), \
         patch("wake_word.find_input_device") as mock_find:
        mock_find.return_value = (default_index, device_info['default_samplerate'])
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

    def test_no_audio_reopens_stream_on_new_device(self):
        """Regression: previously the retry only re-resolved the device and
        discarded the result, still reading from the same stale stream. Now
        when find_input_device() returns a DIFFERENT device on timeout, the
        stream must actually be closed and reopened (sd.InputStream called
        again) with the new device - real recovery, not just a log line."""
        detector = _make_detector(11, {"name": "x", "default_samplerate": 48000.0})

        import queue as queue_module

        class _StopTest(Exception):
            pass

        call_count = {"n": 0}

        def _fake_get(timeout=None):
            call_count["n"] += 1
            if call_count["n"] >= 2:
                # End the test after the reopened stream's inner loop has
                # been entered once.
                raise _StopTest()
            raise queue_module.Empty()

        mock_stream = MagicMock()
        mock_stream.__enter__.return_value = mock_stream

        with patch("wake_word.sd") as mock_sd, \
             patch("wake_word.find_input_device") as mock_find, \
             patch("builtins.print") as mock_print:
            mock_sd.InputStream.side_effect = lambda *a, **kw: mock_stream
            # Different device/rate than the one the detector was built with.
            mock_find.return_value = (99, 16000.0)

            with patch("queue.Queue") as mock_queue_cls:
                mock_queue = MagicMock()
                mock_queue.get.side_effect = _fake_get
                mock_queue_cls.return_value = mock_queue

                with self.assertRaises(_StopTest):
                    detector.listen_for_wake()

            printed = [str(c.args[0]) for c in mock_print.call_args_list if c.args]
            self.assertTrue(
                any("[WAKE] No audio from input device" in p for p in printed)
            )
            # Re-resolves the mic once on the no-audio path.
            mock_find.assert_called_once()
            # Stream was reopened with the new device: InputStream invoked
            # twice (initial open + reopen), and the detector's device/rate
            # were updated.
            self.assertEqual(mock_sd.InputStream.call_count, 2)
            second_call_kwargs = mock_sd.InputStream.call_args_list[1].kwargs
            self.assertEqual(second_call_kwargs["device"], 99)
            self.assertEqual(second_call_kwargs["samplerate"], 16000.0)
            self.assertEqual(detector.device, 99)
            self.assertEqual(detector.capture_rate, 16000.0)

    def test_no_audio_same_device_does_not_reopen_stream(self):
        """When find_input_device() resolves to the SAME device on timeout,
        the stream must NOT be needlessly reopened (no stream churn) - just
        keep waiting on the already-open stream."""
        detector = _make_detector(11, {"name": "x", "default_samplerate": 48000.0})

        import queue as queue_module

        class _StopTest(Exception):
            pass

        call_count = {"n": 0}

        def _fake_get(timeout=None):
            call_count["n"] += 1
            if call_count["n"] >= 3:
                # Let a couple of timeouts pass on the same open stream.
                raise _StopTest()
            raise queue_module.Empty()

        mock_stream = MagicMock()
        mock_stream.__enter__.return_value = mock_stream

        with patch("wake_word.sd") as mock_sd, \
             patch("wake_word.find_input_device") as mock_find, \
             patch("builtins.print") as mock_print:
            mock_sd.InputStream.side_effect = lambda *a, **kw: mock_stream
            # Same device/rate the detector was already built with.
            mock_find.return_value = (11, 48000.0)

            with patch("queue.Queue") as mock_queue_cls:
                mock_queue = MagicMock()
                mock_queue.get.side_effect = _fake_get
                mock_queue_cls.return_value = mock_queue

                with self.assertRaises(_StopTest):
                    detector.listen_for_wake()

            printed = [str(c.args[0]) for c in mock_print.call_args_list if c.args]
            # Warned exactly once (not once per timeout while still stalled).
            warn_count = sum(
                1 for p in printed if "[WAKE] No audio from input device" in p
            )
            self.assertEqual(warn_count, 1)
            # Re-resolved once, but stream was NOT reopened - only the
            # initial InputStream call should have happened.
            mock_find.assert_called_once()
            self.assertEqual(mock_sd.InputStream.call_count, 1)


class TestStreamOpenFailure(unittest.TestCase):

    def test_open_failure_retries_and_succeeds(self):
        """sd.InputStream() raising on the first attempt must not crash
        listen_for_wake() — it should re-resolve the mic and retry."""
        detector = _make_detector(11, {"name": "x", "default_samplerate": 48000.0})

        mock_stream = MagicMock()
        mock_stream.__enter__.return_value = mock_stream

        import queue as queue_module

        class _StopTest(Exception):
            pass

        def _fake_get(timeout=None):
            raise _StopTest()

        attempts = {"n": 0}

        def _ctor(*args, **kwargs):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise Exception("Device unavailable [PaErrorCode -9985]")
            return mock_stream

        with patch("wake_word.sd") as mock_sd, \
             patch("wake_word.find_input_device") as mock_find, \
             patch("wake_word.time.sleep") as mock_sleep, \
             patch("builtins.print") as mock_print:
            mock_sd.InputStream.side_effect = _ctor
            mock_find.return_value = (12, 44100.0)

            with patch("queue.Queue") as mock_queue_cls:
                mock_queue = MagicMock()
                mock_queue.get.side_effect = _fake_get
                mock_queue_cls.return_value = mock_queue

                with self.assertRaises(_StopTest):
                    detector.listen_for_wake()

            self.assertEqual(mock_sd.InputStream.call_count, 2)
            mock_find.assert_called_once()
            mock_sleep.assert_called_once_with(2)
            self.assertEqual(detector.device, 12)
            self.assertEqual(detector.capture_rate, 44100.0)
            printed = [str(c.args[0]) for c in mock_print.call_args_list if c.args]
            self.assertTrue(any("Failed to open input device" in p for p in printed))

    def test_open_failure_keeps_retrying_with_backoff(self):
        """A genuinely dead mic (open keeps failing) must not spin-loop or
        crash — it should back off between attempts and keep retrying."""
        detector = _make_detector(11, {"name": "x", "default_samplerate": 48000.0})

        _MAX_ATTEMPTS = 5
        attempts = {"n": 0}

        # BaseException (not Exception) so it isn't swallowed by the
        # open-retry loop's own `except Exception` — this lets the test
        # deterministically stop the (otherwise infinite) retry loop after
        # a bounded number of attempts.
        class _StopTest(BaseException):
            pass

        def _ctor(*args, **kwargs):
            attempts["n"] += 1
            if attempts["n"] >= _MAX_ATTEMPTS:
                raise _StopTest()
            raise Exception("Device unavailable [PaErrorCode -9985]")

        with patch("wake_word.sd") as mock_sd, \
             patch("wake_word.find_input_device") as mock_find, \
             patch("wake_word.time.sleep") as mock_sleep, \
             patch("builtins.print"):
            mock_sd.InputStream.side_effect = _ctor
            mock_find.return_value = (11, 48000.0)

            with self.assertRaises(_StopTest):
                detector.listen_for_wake()

            self.assertEqual(mock_sd.InputStream.call_count, _MAX_ATTEMPTS)
            self.assertEqual(mock_sleep.call_count, _MAX_ATTEMPTS - 1)

    def test_open_failure_with_no_microphone_does_not_propagate(self):
        """find_input_device() raising NoMicrophoneError during the
        open-retry path must not propagate out of listen_for_wake() — it
        should log and keep retrying with backoff, in case the mic is
        reconnected later."""
        detector = _make_detector(11, {"name": "x", "default_samplerate": 48000.0})

        _MAX_ATTEMPTS = 4
        attempts = {"n": 0}

        # BaseException (not Exception) so it isn't swallowed by the
        # open-retry loop's own `except Exception`.
        class _StopTest(BaseException):
            pass

        def _ctor(*args, **kwargs):
            attempts["n"] += 1
            if attempts["n"] >= _MAX_ATTEMPTS:
                raise _StopTest()
            raise Exception("Device unavailable [PaErrorCode -9985]")

        def _find_side_effect():
            raise NoMicrophoneError("No microphone found.")

        with patch("wake_word.sd") as mock_sd, \
             patch("wake_word.find_input_device") as mock_find, \
             patch("wake_word.time.sleep") as mock_sleep, \
             patch("builtins.print") as mock_print:
            mock_sd.InputStream.side_effect = _ctor
            mock_find.side_effect = _find_side_effect

            with self.assertRaises(_StopTest):
                detector.listen_for_wake()

            self.assertEqual(mock_sd.InputStream.call_count, _MAX_ATTEMPTS)
            self.assertEqual(mock_sleep.call_count, _MAX_ATTEMPTS - 1)
            # Device/rate remain unchanged since re-resolution never
            # succeeded.
            self.assertEqual(detector.device, 11)
            self.assertEqual(detector.capture_rate, 48000.0)
            printed = [str(c.args[0]) for c in mock_print.call_args_list if c.args]
            self.assertTrue(any("No microphone available" in p for p in printed))


if __name__ == "__main__":
    unittest.main()
