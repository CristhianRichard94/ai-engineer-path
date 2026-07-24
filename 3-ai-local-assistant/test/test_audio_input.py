"""
test/test_audio_input.py — Unit tests for jarvis/audio_input.py's shared mic
resolution logic (find_input_device).

sounddevice is mocked so tests run without a mic or network access.
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

if "sounddevice" not in sys.modules:
    sys.modules["sounddevice"] = MagicMock()

import audio_input as audio_input_module
from audio_input import find_input_device, NoMicrophoneError


class TestFindInputDevice(unittest.TestCase):

    def test_default_device_present_and_valid_is_used(self):
        with patch.object(audio_input_module, "sd") as mock_sd:
            mock_sd.default.device = (3, 3)
            mock_sd.query_devices.return_value = {
                "name": "Realtek Mic Array",
                "default_samplerate": 48000.0,
            }
            index, rate = find_input_device()
        self.assertEqual(index, 3)
        self.assertEqual(rate, 48000.0)
        mock_sd.query_devices.assert_called_once_with(3)

    def test_default_absent_falls_back_to_scan_and_finds_real_device(self):
        with patch.object(audio_input_module, "sd") as mock_sd:
            mock_sd.default.device = (-1, -1)
            mock_sd.query_devices.return_value = [
                {"name": "Speakers", "max_input_channels": 0, "default_samplerate": 48000.0},
                {"name": "Realtek Mic Array", "max_input_channels": 2, "default_samplerate": 44100.0},
            ]
            index, rate = find_input_device()
        self.assertEqual(index, 1)
        self.assertEqual(rate, 44100.0)

    def test_virtual_device_present_but_real_device_preferred(self):
        with patch.object(audio_input_module, "sd") as mock_sd:
            mock_sd.default.device = (-1, -1)
            mock_sd.query_devices.return_value = [
                {"name": "CABLE Output (VB-Audio Virtual Cable)", "max_input_channels": 2, "default_samplerate": 48000.0},
                {"name": "Stereo Mix", "max_input_channels": 2, "default_samplerate": 48000.0},
                {"name": "Bluetooth Headset Mic", "max_input_channels": 1, "default_samplerate": 16000.0},
            ]
            index, rate = find_input_device()
        self.assertEqual(index, 2)
        self.assertEqual(rate, 16000.0)

    def test_all_devices_virtual_falls_back_to_first_rather_than_raising(self):
        with patch.object(audio_input_module, "sd") as mock_sd:
            mock_sd.default.device = (-1, -1)
            mock_sd.query_devices.return_value = [
                {"name": "Stereo Mix", "max_input_channels": 2, "default_samplerate": 48000.0},
                {"name": "CABLE Output", "max_input_channels": 2, "default_samplerate": 48000.0},
            ]
            index, rate = find_input_device()
        self.assertEqual(index, 0)
        self.assertEqual(rate, 48000.0)

    def test_zero_input_capable_devices_raises_no_microphone_error(self):
        with patch.object(audio_input_module, "sd") as mock_sd:
            mock_sd.default.device = (-1, -1)
            mock_sd.query_devices.return_value = [
                {"name": "Speakers", "max_input_channels": 0, "default_samplerate": 48000.0},
            ]
            with self.assertRaises(NoMicrophoneError):
                find_input_device()

    def test_default_device_virtual_falls_back_to_scan_and_finds_real_device(self):
        # Regression: a common real misconfiguration is the OS default
        # recording device being set to a virtual/loopback device (e.g.
        # Windows "Stereo Mix"). That must not be returned unfiltered - it
        # should fall through to the scan-and-filter fallback like an
        # absent default would.
        with patch.object(audio_input_module, "sd") as mock_sd:
            mock_sd.default.device = (4, 4)

            def _query(index=None):
                if index == 4:
                    return {"name": "Stereo Mix", "default_samplerate": 48000.0}
                return [
                    {"name": "Stereo Mix", "max_input_channels": 2, "default_samplerate": 48000.0},
                    {"name": "Bluetooth Headset Mic", "max_input_channels": 1, "default_samplerate": 16000.0},
                ]

            mock_sd.query_devices.side_effect = _query
            index, rate = find_input_device()
        self.assertEqual(index, 1)
        self.assertEqual(rate, 16000.0)

    def test_default_index_query_fails_falls_back_to_scan(self):
        with patch.object(audio_input_module, "sd") as mock_sd:
            mock_sd.default.device = (5, 5)

            def _query(index=None):
                if index == 5:
                    raise Exception("device unavailable")
                return [
                    {"name": "Realtek Mic Array", "max_input_channels": 2, "default_samplerate": 44100.0},
                ]

            mock_sd.query_devices.side_effect = _query
            index, rate = find_input_device()
        self.assertEqual(index, 0)
        self.assertEqual(rate, 44100.0)


if __name__ == "__main__":
    unittest.main()
