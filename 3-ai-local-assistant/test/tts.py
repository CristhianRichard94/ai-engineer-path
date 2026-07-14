"""
test/tts.py — Unit tests for Speaker fallback chain (Fish Speech -> ElevenLabs -> pyttsx3).

pyttsx3, sounddevice, requests, scipy playback are all mocked so tests run
without audio hardware, network, or a real TTS engine.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

for mod in ("pyttsx3", "sounddevice"):
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

import tts as tts_module
from tts import Speaker


def _make_speaker(**env):
    with patch.dict(os.environ, env, clear=False):
        with patch.object(Speaker, "_pyttsx3_run"):  # never start a real worker thread
            speaker = Speaker()
    return speaker


class TestFishSpeechPrimary(unittest.TestCase):

    def test_fish_speech_success_skips_other_backends(self):
        speaker = _make_speaker()
        with patch("requests.post") as mock_post, \
             patch.object(speaker, "_play_wav_bytes") as mock_play, \
             patch.object(speaker, "_try_elevenlabs") as mock_el, \
             patch.object(speaker, "_pyttsx3_speak") as mock_pytts:
            mock_post.return_value = MagicMock(status_code=200, content=b"RIFF....")
            speaker.speak("hello")
            mock_play.assert_called_once()
            mock_el.assert_not_called()
            mock_pytts.assert_not_called()

    def test_fish_speech_non_200_falls_back(self):
        speaker = _make_speaker()
        with patch("requests.post") as mock_post, \
             patch.object(speaker, "_try_elevenlabs", return_value=False) as mock_el, \
             patch.object(speaker, "_pyttsx3_speak") as mock_pytts:
            mock_post.return_value = MagicMock(status_code=500, content=b"")
            speaker.speak("hello")
            mock_el.assert_called_once()
            mock_pytts.assert_called_once()

    def test_fish_speech_exception_falls_back(self):
        speaker = _make_speaker()
        with patch("requests.post", side_effect=ConnectionError("down")), \
             patch.object(speaker, "_try_elevenlabs", return_value=False) as mock_el, \
             patch.object(speaker, "_pyttsx3_speak") as mock_pytts:
            speaker.speak("hello")
            mock_el.assert_called_once()
            mock_pytts.assert_called_once()


class TestElevenLabsSecondary(unittest.TestCase):

    def test_no_key_or_voice_returns_false_without_calling_api(self):
        speaker = _make_speaker(ELEVENLABS_API_KEY="", ELEVENLABS_VOICE_ID="")
        self.assertFalse(speaker._try_elevenlabs("hi"))

    def test_missing_elevenlabs_package_falls_back_to_pyttsx3(self):
        speaker = _make_speaker(ELEVENLABS_API_KEY="key", ELEVENLABS_VOICE_ID="voice")
        with patch("requests.post", side_effect=ConnectionError("no fish")), \
             patch.object(speaker, "_pyttsx3_speak") as mock_pytts:
            # elevenlabs package isn't installed in test env -> ImportError inside
            # _try_elevenlabs is caught internally, so speak() should still resolve.
            speaker.speak("hello")
            mock_pytts.assert_called_once()


class TestPyttsx3LastResort(unittest.TestCase):

    def test_pyttsx3_speak_called_as_last_resort(self):
        speaker = _make_speaker()
        with patch("requests.post", side_effect=ConnectionError("down")), \
             patch.object(speaker, "_try_elevenlabs", return_value=False), \
             patch.object(speaker, "_pyttsx3_speak") as mock_speak:
            speaker.speak("hello")
            mock_speak.assert_called_once_with("hello")


if __name__ == "__main__":
    unittest.main()
