"""
test/router.py — Unit tests for IntentRouter.

All external side-effects (subprocess, requests, pycaw, psutil, Spotify,
AudioSwitcher) are mocked so the test suite runs without real hardware or
network access.
"""

import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch, call

# ── Path setup ──────────────────────────────────────────────────────────
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
JARVIS_DIR = os.path.join(ROOT, "jarvis")
if JARVIS_DIR not in sys.path:
    sys.path.insert(0, JARVIS_DIR)

# Stub heavy optional packages before importing router so we never need them
# installed in the test environment. `anthropic`/`openai` are only stubbed
# if genuinely unavailable — unconditionally overwriting sys.modules here
# would clobber the real package for other test modules (e.g.
# test_claude_client.py) that import this file first during collection and
# need real anthropic exception types to construct.
import importlib  # noqa: E402
for mod in ("pycaw", "pycaw.pycaw", "comtypes", "spotipy",
            "spotipy.oauth2", "spotipy.exceptions", "anthropic"):
    if mod in sys.modules:
        continue
    try:
        importlib.import_module(mod)
    except ImportError:
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
        mock_popen.assert_called_once_with(["notepad.exe"])

    @patch("router.subprocess.Popen")
    def test_open_app_unknown_app_passes_name_directly(self, mock_popen):
        self.router.open_app({"app": "my_custom_app.exe"})
        mock_popen.assert_called_once_with(["my_custom_app.exe"])

    @patch("router.subprocess.Popen")
    def test_open_app_case_insensitive(self, mock_popen):
        self.router.open_app({"app": "Notepad"})
        mock_popen.assert_called_once_with(["notepad.exe"])

    @patch("router.subprocess.Popen")
    def test_open_app_does_not_use_shell(self, mock_popen):
        """Hardening: no shell=True and no shell-string command — the exe
        name ultimately originates from user-controlled text (voice
        transcript / /chat message) via GPT's intent classification."""
        self.router.open_app({"app": "; rm -rf / #"})
        args, kwargs = mock_popen.call_args
        self.assertIsInstance(args[0], list)
        self.assertNotIn("shell", kwargs)

    @patch("router.subprocess.Popen")
    @patch.dict("router.os.environ", {"USERNAME": "testuser"})
    def test_open_app_expands_env_vars(self, mock_popen):
        """Regression: list-form Popen skips shell env-var expansion, so
        %USERNAME%-style paths (e.g. spotify) must be expanded in Python
        before being passed as argv, or the launch fails with WinError 2."""
        self.router.open_app({"app": "spotify"})
        args, _ = mock_popen.call_args
        self.assertIn("testuser", args[0][0])
        self.assertNotIn("%USERNAME%", args[0][0])

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
            ["explorer", r"C:\Users\Cristhian\Documents"]
        )

    @patch("router.subprocess.Popen")
    def test_open_folder_does_not_use_shell(self, mock_popen):
        """Hardening: list-form argv avoids shell metacharacter injection
        from a path containing quotes/`&`/`|` etc — `p["path"]` ultimately
        originates from user-controlled text via GPT's intent parsing."""
        self.router.open_folder({"path": r'C:\evil" & calc.exe & "'})
        args, kwargs = mock_popen.call_args
        self.assertIsInstance(args[0], list)
        self.assertNotIn("shell", kwargs)


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


# ════════════════════════════════════════════════════════════════════════
# ask_claude / daily_task_reminder / _call_claude_cli
# ════════════════════════════════════════════════════════════════════════

class TestClaudeCli(unittest.TestCase):

    def setUp(self):
        self.router = _make_router()

    def test_ask_claude_empty_query_sets_pending_and_prompts(self):
        reply = self.router.ask_claude({"query": ""})
        self.assertIn("ask", reply.lower())
        pending = dict(self.router._pending)
        pending.pop("_ts", None)
        self.assertEqual(pending, {"intent": "ask_claude"})
        self.assertIn("_ts", self.router._pending)

    def test_ask_claude_with_query_sets_confirm_pending_not_dispatch(self):
        # Security gate: a query must never hit the CLI without an explicit
        # "yes" from the user first.
        reply = self.router.ask_claude({"query": "summarize the repo"})
        pending = dict(self.router._pending)
        pending.pop("_ts", None)
        self.assertEqual(
            pending,
            {"intent": "ask_claude_confirm", "query": "summarize the repo"},
        )
        self.assertIn("summarize the repo", reply)
        self.assertIn("confirm", reply.lower())

    def test_daily_task_reminder_sets_confirm_pending_not_dispatch(self):
        reply = self.router.daily_task_reminder({})
        pending = dict(self.router._pending)
        pending.pop("_ts", None)
        self.assertEqual(pending, {"intent": "daily_task_reminder_confirm"})
        self.assertIn("confirm", reply.lower())

    @patch("router.append_claude_audit")
    @patch("router.retrieve", return_value=[])
    def test_ask_claude_sdk_success_logs_success_audit(self, mock_retrieve, mock_audit):
        self.router._claude = MagicMock()
        self.router._claude.ask.return_value = ("Here you go, sir.", None)

        reply = self.router._ask_claude_sdk("summarize the repo")

        self.assertEqual(reply, "Here you go, sir.")
        mock_audit.assert_called_once_with("summarize the repo", "Here you go, sir.", "", 0)

    @patch("router.append_claude_audit")
    @patch("router.retrieve", return_value=[])
    def test_ask_claude_sdk_failure_logs_real_error_not_fake_success(self, mock_retrieve, mock_audit):
        # Regression test: previously append_claude_audit was always called
        # with stderr="" and returncode=0 even when ClaudeClient.ask()
        # internally caught an error, hiding real SDK failures from the
        # audit log.
        self.router._claude = MagicMock()
        self.router._claude.ask.return_value = (
            "Sorry, sir, I couldn't reach Claude for that.",
            "APIConnectionError: could not connect",
        )

        reply = self.router._ask_claude_sdk("summarize the repo")

        self.assertIn("couldn't reach claude", reply.lower())
        mock_audit.assert_called_once_with(
            "summarize the repo",
            "Sorry, sir, I couldn't reach Claude for that.",
            "APIConnectionError: could not connect",
            None,
        )

    @patch("router.shutil.which", return_value=None)
    def test_call_claude_cli_missing_binary_returns_graceful_reply(self, mock_which):
        reply = self.router._call_claude_cli("hello")
        self.assertIn("isn't installed", reply.lower())

    @patch("router.shutil.which", return_value="C:\\fake\\claude.exe")
    @patch("router.subprocess.run", side_effect=router_module.subprocess.TimeoutExpired(cmd="claude", timeout=90))
    def test_call_claude_cli_timeout_returns_graceful_reply(self, mock_run, mock_which):
        reply = self.router._call_claude_cli("hello")
        self.assertIn("couldn't reach claude", reply.lower())

    @patch("router.shutil.which", return_value="C:\\fake\\claude.exe")
    @patch("router.subprocess.run", side_effect=Exception("boom"))
    def test_call_claude_cli_unexpected_exception_returns_graceful_reply(self, mock_run, mock_which):
        reply = self.router._call_claude_cli("hello")
        self.assertIn("couldn't reach claude", reply.lower())

    @patch("router.shutil.which", return_value="C:\\fake\\claude.exe")
    @patch("router.subprocess.run")
    def test_call_claude_cli_nonzero_returncode_returns_graceful_reply(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="oops")
        reply = self.router._call_claude_cli("hello")
        self.assertIn("couldn't reach claude", reply.lower())

    @patch("router.shutil.which", return_value="C:\\fake\\claude.exe")
    @patch("router.subprocess.run")
    def test_call_claude_cli_success_truncates_long_output(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(returncode=0, stdout="x" * 2000, stderr="")
        reply = self.router._call_claude_cli("hello")
        self.assertTrue(reply.endswith("...(truncated)"))
        self.assertLessEqual(len(reply), 800 + len("...(truncated)"))

    @patch("router.shutil.which", return_value="C:\\fake\\claude.exe")
    @patch("router.subprocess.run")
    def test_call_claude_cli_uses_plan_permission_mode(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        self.router._call_claude_cli("hello")
        args, kwargs = mock_run.call_args
        cmd = args[0]
        self.assertIn("--permission-mode", cmd)
        self.assertEqual(cmd[cmd.index("--permission-mode") + 1], "plan")

    @patch("router.shutil.which", return_value="C:\\fake\\claude.exe")
    @patch("router.subprocess.run")
    def test_call_claude_cli_applies_allowed_tools(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        self.router._call_claude_cli(
            "hello", allowed_tools=["mcp__project-tracker__list_open_tasks"]
        )
        args, kwargs = mock_run.call_args
        cmd = args[0]
        self.assertIn("--allowedTools", cmd)
        self.assertIn("mcp__project-tracker__list_open_tasks", cmd)

    @patch("router.append_claude_audit")
    @patch("router.shutil.which", return_value="C:\\fake\\claude.exe")
    @patch("router.subprocess.run")
    def test_call_claude_cli_writes_audit_log_on_success(self, mock_run, mock_which, mock_audit):
        mock_run.return_value = MagicMock(returncode=0, stdout="the result", stderr="")
        self.router._call_claude_cli("hello")
        mock_audit.assert_called_once_with("hello", "the result", "", 0)

    @patch("router.append_claude_audit")
    @patch("router.shutil.which", return_value="C:\\fake\\claude.exe")
    @patch("router.subprocess.run", side_effect=router_module.subprocess.TimeoutExpired(cmd="claude", timeout=90))
    def test_call_claude_cli_writes_audit_log_on_timeout(self, mock_run, mock_which, mock_audit):
        self.router._call_claude_cli("hello")
        mock_audit.assert_called_once()
        args, kwargs = mock_audit.call_args
        self.assertEqual(args[0], "hello")
        self.assertIsNone(args[3])

    @patch("router.shutil.which", return_value="C:\\fake\\claude.exe")
    @patch("router.subprocess.run")
    def test_daily_task_reminder_falls_back_to_cli_prompt_is_one_shot(self, mock_run, mock_which):
        # Fallback path (direct MCP call failing) should still use the
        # one-shot CLI prompt.
        mock_run.return_value = MagicMock(returncode=0, stdout="What's on the docket, sir?", stderr="")
        self.router._set_pending({"intent": "daily_task_reminder_confirm"})
        with patch("router.project_tracker_mcp.call_tool",
                    side_effect=router_module.project_tracker_mcp.ProjectTrackerMCPError("no node")):
            reply = self.router.dispatch({"intent": "chat", "params": {}, "reply": "yes"}, raw_text="yes")
        self.assertEqual(reply, "What's on the docket, sir?")
        args, kwargs = mock_run.call_args
        prompt = args[0][2]
        self.assertIn("list_open_tasks", prompt)
        self.assertIn("one-shot", prompt.lower())
        self.assertNotIn("wait for my answer", prompt.lower())

    # ── Confirmation gate: ask_claude ───────────────────────────────────

    def test_ask_claude_confirm_pending_affirmative_dispatches_cli(self):
        self.router._set_pending({"intent": "ask_claude_confirm", "query": "summarize the repo"})
        with patch.object(self.router, "_ask_claude_sdk", return_value="Done, sir.") as mock_sdk:
            reply = self.router.dispatch({"intent": "chat", "params": {}, "reply": "yes"}, raw_text="yes")
        mock_sdk.assert_called_once_with("summarize the repo")
        self.assertEqual(reply, "Done, sir.")
        self.assertIsNone(self.router._pending)

    def test_ask_claude_confirm_pending_negative_cancels(self):
        self.router._set_pending({"intent": "ask_claude_confirm", "query": "summarize the repo"})
        with patch.object(self.router, "_ask_claude_sdk") as mock_sdk:
            reply = self.router.dispatch({"intent": "chat", "params": {}, "reply": "no"}, raw_text="no thanks")
        mock_sdk.assert_not_called()
        self.assertIn("cancelled", reply.lower())
        self.assertIsNone(self.router._pending)

    def test_ask_claude_confirm_pending_unrelated_reply_cancels(self):
        # Anything that isn't an explicit affirmative must be treated as a
        # cancel, not silently re-prompted or (worse) executed.
        self.router._set_pending({"intent": "ask_claude_confirm", "query": "summarize the repo"})
        with patch.object(self.router, "_ask_claude_sdk") as mock_sdk:
            reply = self.router.dispatch({"intent": "chat", "params": {}, "reply": "what's the weather"},
                                          raw_text="what's the weather")
        mock_sdk.assert_not_called()
        self.assertIn("cancelled", reply.lower())

    def test_ask_claude_full_dispatch_round_trip_pending_confirm_execute(self):
        """Full round trip through dispatch(): fresh ask_claude call with a
        query -> confirmation prompt -> user says yes -> the SDK path actually
        gets invoked. Exercises dispatch()'s pending-routing, not just the
        handler methods directly."""
        with patch.object(self.router, "_ask_claude_sdk", return_value="Repo summarized, sir.") as mock_sdk:
            first_reply = self.router.dispatch(
                {"intent": "ask_claude", "params": {"query": "summarize the repo"}, "reply": "unused"}
            )
            self.assertIn("confirm", first_reply.lower())
            self.assertIn("summarize the repo", first_reply)
            mock_sdk.assert_not_called()

            second_reply = self.router.dispatch(
                {"intent": "chat", "params": {}, "reply": "yes"}, raw_text="yes"
            )

        mock_sdk.assert_called_once_with("summarize the repo")
        self.assertEqual(second_reply, "Repo summarized, sir.")
        self.assertIsNone(self.router._pending)

    # ── Confirmation gate: daily_task_reminder ──────────────────────────

    def test_daily_task_reminder_confirm_pending_affirmative_calls_mcp_direct(self):
        self.router._set_pending({"intent": "daily_task_reminder_confirm"})
        with patch("router.project_tracker_mcp.call_tool",
                    return_value="  1. Fix the bug (created 2026-07-20)") as mock_call:
            with patch.object(self.router, "_call_claude_cli") as mock_cli:
                reply = self.router.dispatch({"intent": "chat", "params": {}, "reply": "yes"}, raw_text="yes")
        mock_call.assert_called_once_with("list_open_tasks")
        mock_cli.assert_not_called()
        self.assertIn("Fix the bug", reply)
        self.assertIn("sir", reply)

    def test_daily_task_reminder_confirm_no_open_tasks_says_none(self):
        self.router._set_pending({"intent": "daily_task_reminder_confirm"})
        with patch("router.project_tracker_mcp.call_tool", return_value="No open tasks."):
            reply = self.router.dispatch({"intent": "chat", "params": {}, "reply": "yes"}, raw_text="yes")
        self.assertIn("no open tasks", reply.lower())

    def test_daily_task_reminder_confirm_mcp_failure_falls_back_to_cli(self):
        self.router._set_pending({"intent": "daily_task_reminder_confirm"})
        with patch("router.project_tracker_mcp.call_tool",
                    side_effect=router_module.project_tracker_mcp.ProjectTrackerMCPError("boom")):
            with patch.object(self.router, "_call_claude_cli", return_value="Here's the docket, sir.") as mock_cli:
                reply = self.router.dispatch({"intent": "chat", "params": {}, "reply": "yes"}, raw_text="yes")
        mock_cli.assert_called_once_with(
            self.router._DAILY_TASK_PROMPT,
            allowed_tools=["mcp__project-tracker__list_open_tasks"],
        )
        self.assertEqual(reply, "Here's the docket, sir.")

    def test_daily_task_reminder_confirm_pending_negative_cancels(self):
        self.router._set_pending({"intent": "daily_task_reminder_confirm"})
        with patch("router.project_tracker_mcp.call_tool") as mock_call:
            with patch.object(self.router, "_call_claude_cli") as mock_cli:
                reply = self.router.dispatch({"intent": "chat", "params": {}, "reply": "no"}, raw_text="no")
        mock_call.assert_not_called()
        mock_cli.assert_not_called()
        self.assertIn("cancelled", reply.lower())

    # ── Pending TTL / expiry ─────────────────────────────────────────────

    def test_stale_pending_is_dropped_and_message_processed_fresh(self):
        # A pending clarification older than _PENDING_TTL_SECONDS must be
        # treated as abandoned: dispatch() should clear it and process the
        # new message as a fresh intent instead of feeding it into
        # _continue_pending as the (stale) answer.
        self.router._pending = {
            "intent": "ask_claude_confirm",
            "query": "summarize the repo",
            "_ts": time.monotonic() - (self.router._PENDING_TTL_SECONDS + 1),
        }
        self.router.get_time = MagicMock(return_value="It is 3:00 PM, sir.")

        with patch.object(self.router, "_ask_claude_sdk") as mock_sdk:
            reply = self.router.dispatch(
                {"intent": "get_time", "params": {}, "reply": "unused"}
            )

        mock_sdk.assert_not_called()
        self.router.get_time.assert_called_once()
        self.assertEqual(reply, "It is 3:00 PM, sir.")
        self.assertIsNone(self.router._pending)

    def test_fresh_pending_within_ttl_is_still_consumed(self):
        self.router._pending = {
            "intent": "ask_claude_confirm",
            "query": "summarize the repo",
            "_ts": time.monotonic() - (self.router._PENDING_TTL_SECONDS - 1),
        }
        with patch.object(self.router, "_ask_claude_sdk", return_value="Done, sir.") as mock_sdk:
            reply = self.router.dispatch(
                {"intent": "chat", "params": {}, "reply": "yes"}, raw_text="yes"
            )
        mock_sdk.assert_called_once_with("summarize the repo")
        self.assertEqual(reply, "Done, sir.")
        self.assertIsNone(self.router._pending)


class TestSwitchAudioDispatch(unittest.TestCase):

    def setUp(self):
        self.router = _make_router()

    def test_switch_audio_dispatch_routes_to_handler(self):
        self.router._audio.switch = MagicMock(return_value="Switched, sir.")
        parsed = {"intent": "switch_audio", "params": {"device": "headphones"}, "reply": "unused"}
        reply = self.router.dispatch(parsed)
        self.assertEqual(reply, "Switched, sir.")


# ════════════════════════════════════════════════════════════════════════
# manage_task
# ════════════════════════════════════════════════════════════════════════

class TestManageTask(unittest.TestCase):

    def setUp(self):
        self.router = _make_router()

    # ── _last_tasks population from daily_task_reminder ─────────────────

    def test_successful_listing_populates_last_tasks(self):
        self.router._set_pending({"intent": "daily_task_reminder_confirm"})
        with patch(
            "router.project_tracker_mcp.call_tool",
            return_value=(
                "  1. Fix the login bug (created 2026-07-20)\n"
                "  2. Buy groceries (created 2026-07-21)"
            ),
        ):
            self.router.dispatch({"intent": "chat", "params": {}, "reply": "yes"}, raw_text="yes")
        self.assertEqual(self.router._last_tasks, ["Fix the login bug", "Buy groceries"])

    def test_zero_open_tasks_listing_clears_last_tasks(self):
        self.router._last_tasks = ["stale task"]
        self.router._set_pending({"intent": "daily_task_reminder_confirm"})
        with patch("router.project_tracker_mcp.call_tool", return_value="No open tasks."):
            self.router.dispatch({"intent": "chat", "params": {}, "reply": "yes"}, raw_text="yes")
        self.assertEqual(self.router._last_tasks, [])

    def test_failed_listing_leaves_last_tasks_unchanged(self):
        self.router._last_tasks = ["Fix the login bug", "Buy groceries"]
        self.router._set_pending({"intent": "daily_task_reminder_confirm"})
        with patch(
            "router.project_tracker_mcp.call_tool",
            side_effect=router_module.project_tracker_mcp.ProjectTrackerMCPError("boom"),
        ):
            with patch.object(self.router, "_call_claude_cli", return_value="fallback reply"):
                self.router.dispatch({"intent": "chat", "params": {}, "reply": "yes"}, raw_text="yes")
        self.assertEqual(self.router._last_tasks, ["Fix the login bug", "Buy groceries"])

    # ── Ordinal / pronoun resolution ─────────────────────────────────────

    def test_resolve_first_ordinal(self):
        self.router._last_tasks = ["Fix the login bug", "Buy groceries", "Ship the release"]
        resolved, error = self.router._resolve_task_reference("first")
        self.assertEqual(resolved, "Fix the login bug")
        self.assertIsNone(error)

    def test_resolve_1st_ordinal(self):
        self.router._last_tasks = ["Fix the login bug", "Buy groceries"]
        resolved, error = self.router._resolve_task_reference("1st")
        self.assertEqual(resolved, "Fix the login bug")

    def test_resolve_second_ordinal(self):
        self.router._last_tasks = ["Fix the login bug", "Buy groceries"]
        resolved, error = self.router._resolve_task_reference("second")
        self.assertEqual(resolved, "Buy groceries")

    def test_resolve_third_ordinal(self):
        self.router._last_tasks = ["a", "b", "c"]
        resolved, error = self.router._resolve_task_reference("3rd")
        self.assertEqual(resolved, "c")

    def test_resolve_last_ordinal(self):
        self.router._last_tasks = ["a", "b", "c"]
        resolved, error = self.router._resolve_task_reference("last")
        self.assertEqual(resolved, "c")

    def test_resolve_the_first_one_phrasing(self):
        """Issue 3: constants.py's JARVIS_SYSTEM example documents 'the
        first one' as valid model output - it must resolve the same as
        bare 'first'."""
        self.router._last_tasks = ["Fix the login bug", "Buy groceries"]
        resolved, error = self.router._resolve_task_reference("the first one")
        self.assertEqual(resolved, "Fix the login bug")
        self.assertIsNone(error)

    def test_resolve_the_last_one_phrasing(self):
        self.router._last_tasks = ["a", "b", "c"]
        resolved, error = self.router._resolve_task_reference("the last one")
        self.assertEqual(resolved, "c")
        self.assertIsNone(error)

    def test_resolve_that_one_with_single_task(self):
        self.router._last_tasks = ["Fix the login bug"]
        resolved, error = self.router._resolve_task_reference("that one")
        self.assertEqual(resolved, "Fix the login bug")
        self.assertIsNone(error)

    def test_resolve_it_with_single_task(self):
        self.router._last_tasks = ["Fix the login bug"]
        resolved, error = self.router._resolve_task_reference("it")
        self.assertEqual(resolved, "Fix the login bug")

    def test_resolve_that_ambiguous_with_multiple_tasks_is_unresolvable(self):
        self.router._last_tasks = ["Fix the login bug", "Buy groceries"]
        resolved, error = self.router._resolve_task_reference("that")
        self.assertIsNone(resolved)
        self.assertIn("which task", error.lower())

    def test_resolve_ordinal_out_of_range_is_unresolvable(self):
        self.router._last_tasks = ["Fix the login bug"]
        resolved, error = self.router._resolve_task_reference("third")
        self.assertIsNone(resolved)
        self.assertIn("which task", error.lower())

    def test_resolve_ordinal_with_empty_last_tasks_is_unresolvable(self):
        self.router._last_tasks = []
        resolved, error = self.router._resolve_task_reference("first")
        self.assertIsNone(resolved)
        self.assertIn("which task", error.lower())

    def test_resolve_concrete_query_passes_through_unchanged(self):
        self.router._last_tasks = []
        resolved, error = self.router._resolve_task_reference("login bug")
        self.assertEqual(resolved, "login bug")
        self.assertIsNone(error)

    def test_manage_task_unresolvable_ordinal_returns_clarifying_reply_no_pending(self):
        self.router._last_tasks = []
        reply = self.router.manage_task({"action": "done", "query": "first"})
        self.assertIn("which task", reply.lower())
        self.assertIsNone(self.router._pending)

    def test_manage_task_resolves_ordinal_before_setting_pending(self):
        self.router._last_tasks = ["Fix the login bug", "Buy groceries"]
        reply = self.router.manage_task({"action": "done", "query": "first"})
        pending = dict(self.router._pending)
        pending.pop("_ts", None)
        self.assertEqual(pending["query"], "Fix the login bug")
        self.assertIn("Fix the login bug", reply)

    # ── Confirmation gate: manage_task ───────────────────────────────────

    def test_manage_task_done_sets_confirm_pending(self):
        self.router._last_tasks = ["Fix the login bug"]
        reply = self.router.manage_task({"action": "done", "query": "login bug"})
        pending = dict(self.router._pending)
        pending.pop("_ts", None)
        self.assertEqual(
            pending,
            {
                "intent": "manage_task_confirm",
                "action": "done",
                "query": "Fix the login bug",
                "description": "",
                "priority": None,
            },
        )
        self.assertIn("login bug", reply)
        self.assertIn("confirm", reply.lower())

    def test_manage_task_direct_query_no_match_returns_clarifying_no_pending(self):
        """Issue 1 regression: a direct-text query that doesn't match any
        real task must not proceed to a confirmation - it should ask for
        clarification instead, since confirming would mutate/delete an
        arbitrary or wrong row."""
        self.router._last_tasks = ["Fix the login bug", "Buy groceries"]
        reply = self.router.manage_task({"action": "delete", "query": "spotify"})
        self.assertIn("couldn't find a task matching 'spotify'", reply)
        self.assertIsNone(self.router._pending)

    def test_manage_task_direct_query_ambiguous_match_returns_clarifying_no_pending(self):
        self.router._last_tasks = ["Fix the login bug", "Fix the signup bug"]
        reply = self.router.manage_task({"action": "done", "query": "fix"})
        self.assertIn("more than one task", reply.lower())
        self.assertIsNone(self.router._pending)

    def test_manage_task_direct_query_names_real_matched_task_in_confirmation(self):
        """Issue 1: confirmation prompt must echo the real resolved task
        text, not the raw user query."""
        self.router._last_tasks = ["Fix the login bug", "Buy groceries"]
        reply = self.router.manage_task({"action": "delete", "query": "groceries"})
        self.assertIn("Buy groceries", reply)
        pending = dict(self.router._pending)
        self.assertEqual(pending["query"], "Buy groceries")

    def test_manage_task_direct_query_falls_back_to_fresh_listing_when_last_tasks_empty(self):
        self.router._last_tasks = []
        with patch(
            "router.project_tracker_mcp.call_tool",
            return_value="  1. Fix the login bug (created 2026-07-20)",
        ) as mock_call:
            reply = self.router.manage_task({"action": "done", "query": "login bug"})
        mock_call.assert_called_once_with("list_open_tasks")
        self.assertIn("Fix the login bug", reply)
        self.assertEqual(self.router._last_tasks, ["Fix the login bug"])

    def test_manage_task_add_sets_confirm_pending_with_description(self):
        reply = self.router.manage_task({"action": "add", "description": "buy groceries"})
        pending = dict(self.router._pending)
        pending.pop("_ts", None)
        self.assertEqual(pending["action"], "add")
        self.assertEqual(pending["description"], "buy groceries")
        self.assertIn("buy groceries", reply)

    def test_manage_task_add_without_description_asks_for_it_no_pending(self):
        reply = self.router.manage_task({"action": "add", "description": ""})
        self.assertIn("what should the new task say", reply.lower())
        self.assertIsNone(self.router._pending)

    def test_manage_task_confirm_negative_cancels(self):
        self.router._set_pending({
            "intent": "manage_task_confirm", "action": "done",
            "query": "login bug", "description": "", "priority": None,
        })
        with patch("router.project_tracker_mcp.call_tool") as mock_call:
            reply = self.router.dispatch(
                {"intent": "chat", "params": {}, "reply": "no"}, raw_text="no"
            )
        mock_call.assert_not_called()
        self.assertIn("cancelled", reply.lower())
        self.assertIsNone(self.router._pending)

    # ── Execution: mark_task_done ────────────────────────────────────────

    def test_manage_task_done_confirm_affirmative_calls_mcp_direct(self):
        self.router._set_pending({
            "intent": "manage_task_confirm", "action": "done",
            "query": "login bug", "description": "", "priority": None,
        })
        with patch(
            "router.project_tracker_mcp.call_tool",
            return_value="Marked 'Fix the login bug' as done.",
        ) as mock_call:
            reply = self.router.dispatch(
                {"intent": "chat", "params": {}, "reply": "yes"}, raw_text="yes"
            )
        mock_call.assert_called_once_with("mark_task_done", {"query": "login bug"})
        self.assertEqual(reply, "Marked 'Fix the login bug' as done.")
        self.assertIsNone(self.router._pending)

    def test_manage_task_delete_confirm_affirmative_calls_mcp_direct(self):
        self.router._set_pending({
            "intent": "manage_task_confirm", "action": "delete",
            "query": "spotify", "description": "", "priority": None,
        })
        with patch(
            "router.project_tracker_mcp.call_tool",
            return_value="Deleted task 'spotify'.",
        ) as mock_call:
            reply = self.router.dispatch(
                {"intent": "chat", "params": {}, "reply": "yes"}, raw_text="yes"
            )
        mock_call.assert_called_once_with("delete_task", {"query": "spotify"})
        self.assertEqual(reply, "Deleted task 'spotify'.")

    def test_manage_task_add_confirm_affirmative_calls_mcp_direct(self):
        self.router._set_pending({
            "intent": "manage_task_confirm", "action": "add",
            "query": "", "description": "buy groceries", "priority": None,
        })
        with patch(
            "router.project_tracker_mcp.call_tool",
            return_value="Added task 'buy groceries'.",
        ) as mock_call:
            reply = self.router.dispatch(
                {"intent": "chat", "params": {}, "reply": "yes"}, raw_text="yes"
            )
        mock_call.assert_called_once_with("add_task", {"description": "buy groceries"})
        self.assertEqual(reply, "Added task 'buy groceries'.")

    def test_manage_task_add_confirm_with_priority_includes_priority_arg(self):
        self.router._set_pending({
            "intent": "manage_task_confirm", "action": "add",
            "query": "", "description": "buy groceries", "priority": 2,
        })
        with patch(
            "router.project_tracker_mcp.call_tool",
            return_value="Added task 'buy groceries'.",
        ) as mock_call:
            self.router.dispatch(
                {"intent": "chat", "params": {}, "reply": "yes"}, raw_text="yes"
            )
        mock_call.assert_called_once_with(
            "add_task", {"description": "buy groceries", "priority": 2}
        )

    def test_manage_task_edit_confirm_affirmative_calls_mcp_direct(self):
        self.router._set_pending({
            "intent": "manage_task_confirm", "action": "edit",
            "query": "login bug", "description": "Fix the critical login bug",
            "priority": 1,
        })
        with patch(
            "router.project_tracker_mcp.call_tool",
            return_value="Updated task 'login bug'.",
        ) as mock_call:
            reply = self.router.dispatch(
                {"intent": "chat", "params": {}, "reply": "yes"}, raw_text="yes"
            )
        mock_call.assert_called_once_with(
            "edit_task",
            {"query": "login bug", "description": "Fix the critical login bug", "priority": 1},
        )
        self.assertEqual(reply, "Updated task 'login bug'.")

    # ── MCP failure -> CLI fallback ──────────────────────────────────────

    def test_manage_task_done_mcp_failure_falls_back_to_cli(self):
        self.router._set_pending({
            "intent": "manage_task_confirm", "action": "done",
            "query": "login bug", "description": "", "priority": None,
        })
        with patch(
            "router.project_tracker_mcp.call_tool",
            side_effect=router_module.project_tracker_mcp.ProjectTrackerMCPError("boom"),
        ):
            with patch.object(
                self.router, "_call_claude_cli", return_value="Marked it done, sir."
            ) as mock_cli:
                reply = self.router.dispatch(
                    {"intent": "chat", "params": {}, "reply": "yes"}, raw_text="yes"
                )
        mock_cli.assert_called_once()
        args, kwargs = mock_cli.call_args
        self.assertIn("login bug", args[0])
        self.assertEqual(kwargs["allowed_tools"], ["mcp__project-tracker__mark_task_done"])
        self.assertEqual(reply, "Marked it done, sir.")

    # ── Full round trip ───────────────────────────────────────────────────

    def test_manage_task_full_round_trip_first_one_after_listing(self):
        """End-to-end: list tasks -> confirm listing -> 'mark the first one
        done' -> confirm -> mark_task_done called with the resolved text."""
        self.router._set_pending({"intent": "daily_task_reminder_confirm"})
        with patch(
            "router.project_tracker_mcp.call_tool",
            return_value="  1. Fix the login bug (created 2026-07-20)\n  2. Buy groceries (created 2026-07-21)",
        ):
            self.router.dispatch({"intent": "chat", "params": {}, "reply": "yes"}, raw_text="yes")

        self.assertEqual(self.router._last_tasks, ["Fix the login bug", "Buy groceries"])

        confirm_reply = self.router.dispatch({
            "intent": "manage_task",
            "params": {"action": "done", "query": "first"},
            "reply": "unused",
        })
        self.assertIn("Fix the login bug", confirm_reply)
        self.assertIn("confirm", confirm_reply.lower())

        with patch(
            "router.project_tracker_mcp.call_tool",
            return_value="Marked 'Fix the login bug' as done.",
        ) as mock_call:
            final_reply = self.router.dispatch(
                {"intent": "chat", "params": {}, "reply": "yes"}, raw_text="yes"
            )
        mock_call.assert_called_once_with("mark_task_done", {"query": "Fix the login bug"})
        self.assertEqual(final_reply, "Marked 'Fix the login bug' as done.")
        self.assertIsNone(self.router._pending)