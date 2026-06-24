"""
test/router.py — Unit tests for IntentRouter.

All external side-effects (subprocess, requests, pycaw, psutil, Spotify,
AudioSwitcher) are mocked so the test suite runs without real hardware or
network access.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch, call

# ── Path setup ──────────────────────────────────────────────────────────
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Stub heavy optional packages before importing router so we never need them
# installed in the test environment.
for mod in ("pycaw", "pycaw.pycaw", "comtypes", "spotipy",
            "spotipy.oauth2", "spotipy.exceptions"):
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

import router as router_module
from router import IntentRouter


# ── Helpers ─────────────────────────────────────────────────────────────

def _make_router(**env_overrides):
    """Return an IntentRouter with env vars patched and side-effects mocked."""
    env = {
        "OPENWEATHER_API_KEY"  : "test-weather-key",
        "DEFAULT_CITY"         : "TestCity",
        "SPOTIFY_CLIENT_ID"    : "test-id",
        "SPOTIFY_CLIENT_SECRET": "test-secret",
        "SPOTIFY_REDIRECT_URI" : "http://localhost:8888/callback",
        "SPOTIFY_USE_OAUTH"    : "false",
        **env_overrides,
    }
    with patch.dict(os.environ, env):
        with patch("router.AudioSwitcher") as mock_switcher_cls:
            mock_switcher_cls.return_value = MagicMock()
            r = IntentRouter()
    return r


# ════════════════════════════════════════════════════════════════════════
# Dispatch
# ════════════════════════════════════════════════════════════════════════

class TestDispatch(unittest.TestCase):

    def setUp(self):
        self.router = _make_router()

    def test_dispatch_unknown_intent_calls_do_nothing(self):
        # Replace via instance attribute — dispatch uses getattr so patch is seen
        self.router.do_nothing = MagicMock()
        parsed = {"intent": "fly_to_moon", "params": {}, "reply": "Sure."}
        reply = self.router.dispatch(parsed)
        self.router.do_nothing.assert_called_once_with({})
        self.assertEqual(reply, "Sure.")

    def test_dispatch_action_intent_returns_gpt_reply(self):
        self.router.open_app = MagicMock()
        parsed = {"intent": "open_app", "params": {"app": "notepad"}, "reply": "Opening, sir."}
        reply = self.router.dispatch(parsed)
        self.assertEqual(reply, "Opening, sir.")
        self.router.open_app.assert_called_once_with({"app": "notepad"})

    def test_dispatch_data_intent_returns_handler_reply(self):
        self.router.get_time = MagicMock(return_value="It is 3:00 PM, sir.")
        parsed = {"intent": "get_time", "params": {}, "reply": "unused"}
        reply = self.router.dispatch(parsed)
        self.assertEqual(reply, "It is 3:00 PM, sir.")

    def test_dispatch_data_intent_falls_back_to_gpt_reply_when_handler_returns_none(self):
        self.router.get_time = MagicMock(return_value=None)
        parsed = {"intent": "get_time", "params": {}, "reply": "fallback reply"}
        reply = self.router.dispatch(parsed)
        self.assertEqual(reply, "fallback reply")

    def test_dispatch_missing_intent_key_defaults_to_chat(self):
        self.router.do_nothing = MagicMock()
        reply = self.router.dispatch({"params": {}, "reply": "ok"})
        self.router.do_nothing.assert_called_once()
        self.assertEqual(reply, "ok")


# ════════════════════════════════════════════════════════════════════════
# open_app / close_app
# ════════════════════════════════════════════════════════════════════════

class TestOpenCloseApp(unittest.TestCase):

    def setUp(self):
        self.router = _make_router()

    @patch("router.subprocess.Popen")
    def test_open_app_known_app_uses_mapped_exe(self, mock_popen):
        self.router.open_app({"app": "notepad"})
        mock_popen.assert_called_once_with("notepad.exe", shell=True)

    @patch("router.subprocess.Popen")
    def test_open_app_unknown_app_passes_name_directly(self, mock_popen):
        self.router.open_app({"app": "my_custom_app.exe"})
        mock_popen.assert_called_once_with("my_custom_app.exe", shell=True)

    @patch("router.subprocess.Popen")
    def test_open_app_case_insensitive(self, mock_popen):
        self.router.open_app({"app": "Notepad"})
        mock_popen.assert_called_once_with("notepad.exe", shell=True)

    @patch("router.psutil.process_iter")
    def test_close_app_kills_matching_process(self, mock_iter):
        mock_proc = MagicMock()
        mock_proc.info = {"name": "notepad.exe"}
        mock_iter.return_value = [mock_proc]
        self.router.close_app({"app": "notepad"})
        mock_proc.kill.assert_called_once()

    @patch("router.psutil.process_iter")
    def test_close_app_skips_non_matching_process(self, mock_iter):
        mock_proc = MagicMock()
        mock_proc.info = {"name": "chrome.exe"}
        mock_iter.return_value = [mock_proc]
        self.router.close_app({"app": "notepad"})
        mock_proc.kill.assert_not_called()

    @patch("router.psutil.process_iter")
    def test_close_app_strips_exe_suffix(self, mock_iter):
        mock_proc = MagicMock()
        mock_proc.info = {"name": "notepad.exe"}
        mock_iter.return_value = [mock_proc]
        self.router.close_app({"app": "notepad.exe"})
        mock_proc.kill.assert_called_once()


# ════════════════════════════════════════════════════════════════════════
# search_web
# ════════════════════════════════════════════════════════════════════════

class TestSearchWeb(unittest.TestCase):

    def setUp(self):
        self.router = _make_router()

    @patch("router.webbrowser.open")
    def test_search_web_opens_google_url(self, mock_open):
        self.router.search_web({"query": "python asyncio"})
        mock_open.assert_called_once_with(
            "https://google.com/search?q=python asyncio"
        )


# ════════════════════════════════════════════════════════════════════════
# get_time
# ════════════════════════════════════════════════════════════════════════

class TestGetTime(unittest.TestCase):

    def setUp(self):
        self.router = _make_router()

    def test_get_time_returns_formatted_time_string(self):
        reply = self.router.get_time({})
        self.assertIn("sir", reply)
        # Should contain a time pattern like "03:45 PM"
        import re
        self.assertRegex(reply, r"\d{1,2}:\d{2} (AM|PM)")


# ════════════════════════════════════════════════════════════════════════
# get_system_info
# ════════════════════════════════════════════════════════════════════════

class TestGetSystemInfo(unittest.TestCase):

    def setUp(self):
        self.router = _make_router()

    @patch("router.psutil.cpu_percent", return_value=42.0)
    @patch("router.psutil.virtual_memory")
    def test_get_system_info_includes_cpu_and_ram(self, mock_vm, mock_cpu):
        mock_vm.return_value = MagicMock(
            percent=70.0,
            used=8 * (1024 ** 3),
            total=16 * (1024 ** 3),
        )
        reply = self.router.get_system_info({})
        # cpu_percent returns float; format varies (42% or 42.0%)
        self.assertTrue("42" in reply, f"CPU% not in reply: {reply}")
        self.assertTrue("70" in reply, f"RAM% not in reply: {reply}")
        self.assertIn("sir", reply)


# ════════════════════════════════════════════════════════════════════════
# set_volume
# ════════════════════════════════════════════════════════════════════════

class TestSetVolume(unittest.TestCase):

    def setUp(self):
        self.router = _make_router()

    def test_set_volume_dispatched(self):
        # Replace via instance attribute so dispatch (getattr-based) picks it up.
        self.router.set_volume = MagicMock()
        parsed = {"intent": "set_volume", "params": {"level": 75}, "reply": "Volume set."}
        reply = self.router.dispatch(parsed)
        self.router.set_volume.assert_called_once_with({"level": 75})
        self.assertEqual(reply, "Volume set.")


# ════════════════════════════════════════════════════════════════════════
# open_folder
# ════════════════════════════════════════════════════════════════════════

class TestOpenFolder(unittest.TestCase):

    def setUp(self):
        self.router = _make_router()

    @patch("router.subprocess.Popen")
    def test_open_folder_calls_explorer(self, mock_popen):
        self.router.open_folder({"path": r"C:\Users\Cristhian\Documents"})
        mock_popen.assert_called_once_with(
            r'explorer "C:\Users\Cristhian\Documents"'
        )


# ════════════════════════════════════════════════════════════════════════
# get_weather
# ════════════════════════════════════════════════════════════════════════

class TestGetWeather(unittest.TestCase):

    def setUp(self):
        self.router = _make_router()

    def _mock_response(self, json_data, status=200):
        resp = MagicMock()
        resp.json.return_value = json_data
        resp.status_code = status
        resp.raise_for_status.return_value = None
        return resp

    @patch("router.requests.get")
    def test_get_weather_success(self, mock_get):
        mock_get.return_value = self._mock_response({
            "main"   : {"temp": 20, "feels_like": 18, "humidity": 55},
            "weather": [{"description": "clear sky"}],
            "name"   : "TestCity",
        })
        reply = self.router.get_weather({"city": "TestCity"})
        self.assertIn("TestCity", reply)
        self.assertIn("20", reply)
        self.assertIn("clear sky", reply)

    @patch("router.requests.get")
    def test_get_weather_uses_default_city_when_city_is_current(self, mock_get):
        mock_get.return_value = self._mock_response({
            "main"   : {"temp": 15, "feels_like": 13, "humidity": 60},
            "weather": [{"description": "cloudy"}],
            "name"   : "TestCity",
        })
        self.router.get_weather({"city": "current"})
        call_kwargs = mock_get.call_args[1]["params"]
        self.assertEqual(call_kwargs["q"], "TestCity")

    @patch("router.requests.get")
    def test_get_weather_timeout_returns_timeout_message(self, mock_get):
        import requests as req_mod
        mock_get.side_effect = req_mod.exceptions.Timeout()
        reply = self.router.get_weather({"city": "Nowhere"})
        self.assertIn("timed out", reply)

    @patch("router.requests.get")
    def test_get_weather_404_returns_not_found_message(self, mock_get):
        import requests as req_mod
        err_resp = MagicMock()
        err_resp.status_code = 404
        mock_get.return_value.raise_for_status.side_effect = \
            req_mod.exceptions.HTTPError(response=err_resp)
        reply = self.router.get_weather({"city": "Atlantis"})
        self.assertIn("couldn't find", reply)

    @patch("router.requests.get")
    def test_get_weather_generic_error_returns_unable_message(self, mock_get):
        mock_get.side_effect = Exception("network down")
        reply = self.router.get_weather({"city": "Somewhere"})
        self.assertIn("unable", reply.lower())


# ════════════════════════════════════════════════════════════════════════
# play_spotify
# ════════════════════════════════════════════════════════════════════════

class TestPlaySpotify(unittest.TestCase):

    def setUp(self):
        self.router = _make_router()

    def _inject_mock_player(self, return_value: str):
        mock_player = MagicMock()
        mock_player.search_and_play.return_value = return_value
        self.router._spotify = mock_player
        return mock_player

    def test_play_spotify_calls_player_with_query(self):
        mock_player = self._inject_mock_player("Playing 'Africa' by Toto, sir.")
        reply = self.router.play_spotify({"query": "Africa Toto"})
        mock_player.search_and_play.assert_called_once_with("Africa Toto")
        self.assertEqual(reply, "Playing 'Africa' by Toto, sir.")

    def test_play_spotify_empty_query_returns_prompt(self):
        reply = self.router.play_spotify({"query": ""})
        self.assertIn("what to play", reply)

    def test_play_spotify_missing_query_key_returns_prompt(self):
        reply = self.router.play_spotify({})
        self.assertIn("what to play", reply)

    def test_play_spotify_no_credentials_returns_config_message(self):
        self.router._spotify = None
        # patch _get_spotify so it returns None (simulates missing creds)
        with patch.object(self.router, "_get_spotify", return_value=None):
            reply = self.router.play_spotify({"query": "something"})
        self.assertIn("not configured", reply)

    def test_play_spotify_player_returns_not_found(self):
        self._inject_mock_player("No track found for 'xyzzy123', sir.")
        reply = self.router.play_spotify({"query": "xyzzy123"})
        self.assertIn("No track found", reply)

    def test_play_spotify_dispatch_routes_to_handler(self):
        self._inject_mock_player("Playing 'Song', sir.")
        parsed = {"intent": "play_spotify", "params": {"query": "Song"}, "reply": "unused"}
        reply = self.router.dispatch(parsed)
        self.assertEqual(reply, "Playing 'Song', sir.")


# ════════════════════════════════════════════════════════════════════════
# switch_audio
# ════════════════════════════════════════════════════════════════════════

class TestSwitchAudio(unittest.TestCase):

    def setUp(self):
        self.router = _make_router()

    def test_switch_audio_delegates_to_audio_switcher(self):
        self.router._audio.switch = MagicMock(
            return_value="Audio output switched to headphones, sir."
        )
        reply = self.router.switch_audio({"device": "headphones"})
        self.router._audio.switch.assert_called_once_with("headphones")
        self.assertEqual(reply, "Audio output switched to headphones, sir.")

    def test_switch_audio_empty_device_returns_prompt(self):
        reply = self.router.switch_audio({"device": ""})
        self.assertIn("specify", reply.lower())

    def test_switch_audio_missing_device_key_returns_prompt(self):
        reply = self.router.switch_audio({})
        self.assertIn("specify", reply.lower())

    def test_switch_audio_dispatch_routes_to_handler(self):
        self.router._audio