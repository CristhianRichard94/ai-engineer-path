"""
test/audio_switcher.py — Unit tests for AudioSwitcher.

nircmd.exe is never actually called; subprocess.run is mocked throughout.
"""

import os
import sys
import subprocess
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from audio_switcher import AudioSwitcher


def _make_switcher(**env_overrides):
    """Create AudioSwitcher with mocked env vars and a fake nircmd path."""
    env = {
        "AUDIO_DEVICE_SPEAKER"    : "Speakers (Realtek)",
        "AUDIO_DEVICE_HEADPHONES" : "Headphones (Realtek)",
        **env_overrides,
    }
    with patch.dict(os.environ, env, clear=False):
        switcher = AudioSwitcher(nircmd_path="/fake/nircmd.exe")
    return switcher


# ════════════════════════════════════════════════════════════════════════
# Device resolution
# ════════════════════════════════════════════════════════════════════════

class TestDeviceResolution(unittest.TestCase):

    def setUp(self):
        self.sw = _make_switcher()

    @patch("audio_switcher.subprocess.run")
    def test_switch_headphones_alias(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        reply = self.sw.switch("headphones")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertIn("Headphones (Realtek)", args)
        self.assertIn("switched to headphones", reply.lower())

    @patch("audio_switcher.subprocess.run")
    def test_switch_headphone_singular_alias(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        self.sw.switch("headphone")
        args = mock_run.call_args[0][0]
        self.assertIn("Headphones (Realtek)", args)

    @patch("audio_switcher.subprocess.run")
    def test_switch_speaker_alias(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        reply = self.sw.switch("speaker")
        args = mock_run.call_args[0][0]
        self.assertIn("Speakers (Realtek)", args)
        self.assertIn("switched to speaker", reply.lower())

    @patch("audio_switcher.subprocess.run")
    def test_switch_speakers_plural_alias(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        self.sw.switch("speakers")
        args = mock_run.call_args[0][0]
        self.assertIn("Speakers (Realtek)", args)

    @patch("audio_switcher.subprocess.run")
    def test_switch_earphones_alias(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        self.sw.switch("earphones")
        args = mock_run.call_args[0][0]
        self.assertIn("Headphones (Realtek)", args)

    def test_switch_unknown_device_returns_error_reply(self):
        reply = self.sw.switch("bluetooth_magic")
        self.assertIn("don't recognise", reply.lower())
        self.assertIn("bluetooth_magic", reply)

    def test_switch_empty_string_returns_error_reply(self):
        reply = self.sw.switch("")
        self.assertIn("don't recognise", reply.lower())

    @patch("audio_switcher.subprocess.run")
    def test_switch_case_insensitive(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        self.sw.switch("  HEADPHONES  ")
        mock_run.assert_called_once()


# ════════════════════════════════════════════════════════════════════════
# nircmd error handling
# ════════════════════════════════════════════════════════════════════════

class TestNircmdErrors(unittest.TestCase):

    def setUp(self):
        self.sw = _make_switcher()

    @patch("audio_switcher.subprocess.run", side_effect=FileNotFoundError)
    def test_nircmd_not_found_returns_unavailable_message(self, _):
        reply = self.sw.switch("headphones")
        self.assertIn("nircmd.exe", reply)
        self.assertIn("not found", reply.lower())

    @patch("audio_switcher.subprocess.run",
           side_effect=subprocess.CalledProcessError(1, "nircmd"))
    def test_nircmd_nonzero_exit_returns_failed_message(self, _):
        reply = self.sw.switch("headphones")
        self.assertIn("Failed", reply)

    @patch("audio_switcher.subprocess.run", side_effect=RuntimeError("boom"))
    def test_unexpected_exception_returns_generic_error(self, _):
        reply = self.sw.switch("speaker")
        self.assertIn("unexpected error", reply.lower())

    @patch("audio_switcher.subprocess.run")
    def test_successful_switch_returns_confirmation(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        reply = self.sw.switch("speaker")
        self.assertNotIn("error", reply.lower())
        self.assertNotIn("failed", reply.lower())
        self.assertIn("sir", reply)


# ════════════════════════════════════════════════════════════════════════
# nircmd path resolution
# ════════════════════════════════════════════════════════════════════════

class TestNircmdPathResolution(unittest.TestCase):

    def test_explicit_path_used_when_provided(self):
        sw = AudioSwitcher(nircmd_path="/custom/nircmd.exe")
        self.assertEqual(sw.nircmd, "/custom/nircmd.exe")

    def test_env_var_used_when_no_explicit_path(self):
        with patch.dict(os.environ, {"NIRCMD_PATH": "/env/nircmd.exe"}):
            sw = AudioSwitcher()
        self.assertEqual(sw.nircmd, "/env/nircmd.exe")

    def test_default_path_is_switch_audio_output_subdir(self):
        with patch.dict(os.environ, {}, clear=False):
            # Remove NIRCMD_PATH if set
            os.environ.pop("NIRCMD_PATH", None)
            sw = AudioSwitcher()
        self.assertTrue(sw.nircmd.endswith("nircmd.exe"))
        self.assertIn("switch-audio-output", sw.nircmd)


# ════════════════════════════════════════════════════════════════════════
# list_aliases
# ════════════════════════════════════════════════════════════════════════

class TestListAliases(unittest.TestCase):

    def test_list_aliases_returns_all_friendly_names(self):
        sw = _make_switcher()
        aliases = sw.list_aliases()
        self.assertIn("headphones", aliases)
        self.assertIn("speaker", aliases)
        self.assertIn("speakers", aliases)
        self.assertIn("earphones", aliases)
        self.assertEqual(aliases, sorted(aliases))  # should be sorted


if __name__ == "__main__":
    unittest.main()
