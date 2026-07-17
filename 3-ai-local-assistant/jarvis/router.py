"""
router.py - Intent dispatcher for JARVIS.

Maps intent names (from brain.py) to concrete Windows/API actions.
"""

import json
import os
import shutil
import subprocess
import webbrowser
from datetime import datetime

import psutil
import requests

from spotify_player import SpotifyPlayer, SpotifyAuthError
from audio_switcher import AudioSwitcher
from state import append_claude_audit


class IntentRouter:
    def __init__(self):
        self.weather_key  = os.getenv("OPENWEATHER_API_KEY")
        self.default_city = os.getenv("DEFAULT_CITY", "Buenos Aires")

        # Spotify player (lazy-loaded on first use)
        self._spotify = None
        self._audio   = AudioSwitcher()

        # Single-slot pending-clarification state (documented limitation:
        # only one outstanding slot-fill conversation at a time, no
        # generic intent-interruption support).
        self._pending = None

        # Route table: intent name -> method name on this class.
        # Using method NAMES (not bound methods) so that tests can replace
        # instance methods via attribute assignment and dispatch sees the patch.
        self._routes = {
            "open_app"       : "open_app",
            "close_app"      : "close_app",
            "search_web"     : "search_web",
            "get_time"       : "get_time",
            "get_weather"    : "get_weather",
            "get_system_info": "get_system_info",
            "set_volume"     : "set_volume",
            "open_folder"    : "open_folder",
            "play_spotify"   : "play_spotify",
            "switch_audio"   : "switch_audio",
            "new_project"    : "new_project",
            "ask_claude"     : "ask_claude",
            "daily_task_reminder": "daily_task_reminder",
            "goodbye"        : "goodbye",
            "chat"           : "do_nothing",
        }

        # Intents whose handler returns the spoken reply (data-driven)
        self._DATA_INTENTS = {
            "get_weather",
            "get_system_info",
            "get_time",
            "play_spotify",
            "switch_audio",
            "new_project",
            "ask_claude",
            "daily_task_reminder",
        }

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def dispatch(self, parsed, raw_text=None):
        # A prior turn left a slot unfilled (e.g. "play spotify" with no
        # query, or the new_project wizard mid-flow) -> this turn's parsed
        # params are treated as the answer to that slot, not a fresh intent.
        if self._pending is not None:
            return self._continue_pending(parsed, raw_text)

        intent = parsed.get("intent", "chat")
        params = parsed.get("params", {})
        reply  = parsed.get("reply", "Done, sir.")

        method_name = self._routes.get(intent, "do_nothing")
        fn = getattr(self, method_name, self.do_nothing)

        # ponytail: a handler crashing on a missing/malformed param (e.g. a
        # misparsed intent) must not take down the whole session loop -
        # one bad turn should degrade to an apology, not kill the process.
        try:
            if intent in self._DATA_INTENTS:
                result = fn(params)
                return result if result else reply
            else:
                fn(params)
                return reply
        except Exception:
            return "Sorry, sir, I ran into a problem with that."

    # ------------------------------------------------------------------
    # Pending-slot clarification
    # ------------------------------------------------------------------

    def _continue_pending(self, parsed, raw_text=None):
        """Route this turn's input to whichever slot is currently pending."""
        pending = self._pending
        intent = pending["intent"]

        if intent == "switch_audio":
            device = (parsed.get("params", {}) or {}).get("device", "").strip()
            if not device:
                device = (raw_text or "").strip()
            self._pending = None
            if not device:
                return "I still didn't catch the audio device, sir. Let's try again."
            return self.switch_audio({"device": device})

        if intent == "play_spotify":
            query = (parsed.get("params", {}) or {}).get("query", "").strip()
            if not query:
                query = (raw_text or "").strip()
            self._pending = None
            if not query:
                return "I still didn't catch what to play, sir. Let's try again."
            return self.play_spotify({"query": query})

        if intent == "ask_claude":
            query = (parsed.get("params", {}) or {}).get("query", "").strip()
            if not query:
                query = (raw_text or "").strip()
            self._pending = None
            if not query:
                return "I still didn't catch the question, sir. Let's try again."
            return self.ask_claude({"query": query})

        if intent == "ask_claude_confirm":
            query = pending["query"]
            self._pending = None
            if self._is_affirmative(parsed, raw_text):
                return self._call_claude_cli(query)
            return "Okay, cancelled, sir."

        if intent == "daily_task_reminder_confirm":
            self._pending = None
            if self._is_affirmative(parsed, raw_text):
                return self._call_claude_cli(
                    self._DAILY_TASK_PROMPT,
                    allowed_tools=["mcp__project-tracker__list_open_tasks"],
                )
            return "Okay, cancelled, sir."

        if intent == "new_project":
            return self._advance_new_project(parsed, raw_text)

        # Unknown pending intent — clear it defensively rather than get stuck.
        self._pending = None
        return "Let's start over, sir."

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def open_app(self, p):
        apps = {
            "notepad"   : "notepad.exe",
            "chrome"    : r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "explorer"  : "explorer.exe",
            "calculator": "calc.exe",
            "spotify"   : r"C:\Users\%USERNAME%\AppData\Roaming\Spotify\Spotify.exe",
        }
        exe = apps.get(p["app"].lower(), p["app"])
        subprocess.Popen(exe, shell=True)

    def close_app(self, p):
        name = p["app"].lower().replace(".exe", "")
        for proc in psutil.process_iter(["name"]):
            if name in proc.info["name"].lower():
                proc.kill()

    def search_web(self, p):
        query = (p or {}).get("query", "").strip()
        if not query:
            return "What would you like me to search for, sir?"
        webbrowser.open("https://google.com/search?q={}".format(query))

    def get_time(self, p):
        now = datetime.now()
        return "It is {}, sir.".format(now.strftime("%I:%M %p"))

    def get_system_info(self, p):
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory()
        return (
            "CPU at {}%, RAM {}% used "
            "({:.1f} GB of {:.1f} GB), sir.".format(
                cpu,
                ram.percent,
                ram.used / (1024 ** 3),
                ram.total / (1024 ** 3),
            )
        )

    def set_volume(self, p):
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        devices = AudioUtilities.GetSpeakers()
        iface   = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume  = cast(iface, POINTER(IAudioEndpointVolume))
        level   = max(0, min(100, int(p["level"]))) / 100
        volume.SetMasterVolumeLevelScalar(level, None)

    def open_folder(self, p):
        subprocess.Popen('explorer "{}"'.format(p["path"]))

    def play_spotify(self, p):
        query = p.get("query", "").strip()
        if not query:
            self._pending = {"intent": "play_spotify"}
            return "Please tell me what to play, sir."

        player = self._get_spotify()
        if player is None:
            return ("Spotify is not configured, sir. "
                    "Please add your SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to the .env file.")

        try:
            return player.search_and_play(query)
        except SpotifyAuthError as e:
            print("[SPOTIFY] Auth error: {}".format(e))
            return ("Spotify credentials are invalid, sir. "
                    "Please check your SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in the .env file.")
        except Exception as e:
            print("[SPOTIFY] Unexpected error: {}".format(e))
            return "There was an error connecting to Spotify, sir."

    def switch_audio(self, p):
        device = p.get("device", "").strip()
        if not device:
            self._pending = {"intent": "switch_audio"}
            return "Please specify an audio device, sir."
        return self._audio.switch(device)

    # Rewritten for one-shot voice use: `claude -p` is non-interactive and
    # exits after a single response, so the prompt must not imply a live
    # back-and-forth ("ask me... wait for my answer") that can never happen.
    _DAILY_TASK_PROMPT = (
        "Use the mcp__project-tracker__list_open_tasks tool to get open tasks. "
        "Summarize the open tasks (or suggest 2-3 new project ideas if empty/stale) "
        "as your final answer — this is a one-shot request, don't wait for further "
        "input."
    )

    _CLAUDE_REPLY_LIMIT = 800

    # Words that count as an affirmative answer to a pending confirmation.
    _AFFIRMATIVE_WORDS = ("yes", "yeah", "yep", "yup", "sure", "affirmative",
                          "confirm", "go ahead", "do it")

    @classmethod
    def _is_affirmative(cls, parsed, raw_text=None):
        """Check whether the user's turn (raw text or parsed params/reply)
        reads as an affirmative confirmation."""
        candidates = []
        if raw_text:
            candidates.append(raw_text)
        params = (parsed or {}).get("params", {}) or {}
        for v in params.values():
            if isinstance(v, str):
                candidates.append(v)
        reply = (parsed or {}).get("reply", "")
        if reply:
            candidates.append(reply)
        text = " ".join(candidates).lower()
        return any(word in text for word in cls._AFFIRMATIVE_WORDS)

    def ask_claude(self, p):
        query = (p or {}).get("query", "").strip()
        if not query:
            self._pending = {"intent": "ask_claude"}
            return "What would you like to ask Claude, sir?"
        # Confirmation gate: the query comes from voice/ambient audio -> STT
        # -> intent parser -> straight into an agentic CLI with real
        # file-system access. Never dispatch without an explicit "yes".
        self._pending = {"intent": "ask_claude_confirm", "query": query}
        return "You want me to ask Claude: '{}'. Say yes to confirm, sir.".format(query)

    def daily_task_reminder(self, p):
        # Same confirmation gate as ask_claude - this also invokes the
        # agentic CLI (with project-tracker MCP tool access).
        self._pending = {"intent": "daily_task_reminder_confirm"}
        return "Want me to check today's tasks with Claude, sir? Say yes to confirm."

    def _call_claude_cli(self, prompt, allowed_tools=None):
        """Run the Claude Code CLI non-interactively and return a spoken reply.

        List-form argv (no shell=True) — the prompt is passed as a single
        argument, so there is no shell-injection risk regardless of content.

        Runs in `--permission-mode plan` (read-only planning, no file/tool
        mutations) rather than trusting the user's ambient global Claude
        Code permission config, since this call path is triggered by
        unattended voice/ambient audio. Callers that need a specific MCP
        tool (e.g. daily_task_reminder's project-tracker read tool) can
        pass `allowed_tools` to additionally scope via --allowedTools.
        Every invocation is recorded, full and untruncated, to
        claude_cli_audit.jsonl via state.append_claude_audit for
        after-the-fact review.
        """
        if not shutil.which("claude"):
            return "Claude Code isn't installed, sir."

        cmd = ["claude", "-p", prompt, "--permission-mode", "plan"]
        if allowed_tools:
            cmd += ["--allowedTools"] + list(allowed_tools)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=90,
                cwd=os.path.expanduser("~"),
            )
        except subprocess.TimeoutExpired:
            append_claude_audit(prompt, "", "TimeoutExpired after 90s", None)
            return "Sorry, sir, I couldn't reach Claude for that."
        except Exception as e:
            print("[CLAUDE_CLI] Error: {}".format(e))
            append_claude_audit(prompt, "", str(e), None)
            return "Sorry, sir, I couldn't reach Claude for that."

        append_claude_audit(prompt, result.stdout, result.stderr, result.returncode)

        if result.returncode != 0:
            print("[CLAUDE_CLI] Non-zero exit ({}): {}".format(
                result.returncode, result.stderr))
            return "Sorry, sir, I couldn't reach Claude for that."

        reply = result.stdout.strip()
        if not reply:
            return "Claude didn't return anything, sir."
        if len(reply) > self._CLAUDE_REPLY_LIMIT:
            reply = reply[:self._CLAUDE_REPLY_LIMIT].rstrip() + "...(truncated)"
        return reply

    def new_project(self, p):
        """Kick off (or resume) the multi-turn new_project wizard:
        name -> description -> "create a GitHub repo too?" """
        name        = (p.get("name") or "").strip()
        description = (p.get("description") or "").strip()
        self._pending = {
            "intent": "new_project",
            "step": None,
            "name": name,
            "description": description,
        }
        return self._advance_new_project_state()

    def _advance_new_project_state(self):
        """Return the next question for whichever new_project slot is empty."""
        pending = self._pending
        if not pending["name"]:
            pending["step"] = "name"
            return "What would you like to name the project, sir?"
        if not pending["description"]:
            pending["step"] = "description"
            return "Give me a short description of the project, sir."
        pending["step"] = "github"
        return "Should I create a GitHub repository for it as well, sir?"

    def _advance_new_project(self, parsed, raw_text=None):
        """Handle the turn following a new_project question."""
        pending = self._pending
        step = pending.get("step")
        answer_params = parsed.get("params", {}) or {}

        if step == "name":
            name = (answer_params.get("name") or raw_text or "").strip()
            if not name:
                return "Sorry, I didn't catch the project name, sir. What should I call it?"
            pending["name"] = name
            return self._advance_new_project_state()

        if step == "description":
            description = (answer_params.get("description") or raw_text or "").strip()
            if not description:
                return "Sorry, I didn't catch that, sir. Can you describe the project?"
            pending["description"] = description
            return self._advance_new_project_state()

        if step == "github":
            answer_text = raw_text or parsed.get("reply", "") or json.dumps(answer_params)
            want_github = self._parse_yes_no(answer_text)
            self._pending = None
            return self._create_project(pending["name"], pending["description"], want_github)

        # Unexpected step — bail out rather than get stuck.
        self._pending = None
        return "Something went wrong setting up the project, sir."

    @staticmethod
    def _parse_yes_no(text):
        """Plain substring check for yes/no — no NLU needed for this slot."""
        t = (text or "").lower()
        if any(w in t for w in ("yes", "yeah", "yep", "yup", "sure", "affirmative", "please do")):
            return True
        if any(w in t for w in ("no", "nope", "nah", "negative", "don't", "do not")):
            return False
        return False  # unclear answer -> safest default is to skip GitHub

    def _create_project(self, name, description, want_github):
        projects_dir = os.path.expanduser(os.getenv("JARVIS_PROJECTS_DIR", "~/projects"))
        folder_path  = os.path.join(projects_dir, name)

        try:
            os.makedirs(folder_path, exist_ok=True)
        except OSError as e:
            print("[NEW_PROJECT] Failed to create folder: {}".format(e))
            return "I couldn't create the project folder, sir: {}".format(e)

        if not want_github:
            return "Project '{}' created at {}, sir.".format(name, folder_path)

        if not shutil.which("gh"):
            return (
                "Project '{}' created at {}, sir. GitHub CLI isn't available, "
                "so I skipped repository creation.".format(name, folder_path)
            )

        try:
            subprocess.run(
                [
                    "gh", "repo", "create", name,
                    "--description", description,
                    "--private", "--source=.", "--remote=origin",
                ],
                cwd=folder_path,
                check=True,
            )
            return "Project '{}' created at {} with a GitHub repository, sir.".format(name, folder_path)
        except Exception as e:
            print("[NEW_PROJECT] GitHub repo creation failed: {}".format(e))
            return (
                "Project '{}' created at {}, sir, but I couldn't set up "
                "the GitHub repository.".format(name, folder_path)
            )

    def goodbye(self, p):
        # Signals main.py to end the current session; reply comes from GPT
        pass

    def do_nothing(self, p):
        pass

    def get_weather(self, p):
        city = p.get("city", "current")
        if city in ("current", "", None):
            city = self.default_city

        try:
            resp = requests.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={
                    "q"    : city,
                    "appid": self.weather_key,
                    "units": "metric",
                    "lang" : "en",
                },
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()

            temp      = round(data["main"]["temp"])
            feels     = round(data["main"]["feels_like"])
            desc      = data["weather"][0]["description"]
            humidity  = data["main"]["humidity"]
            city_name = data["name"]

            return (
                "{}: {}, {}C, feels like {}C, humidity {}%.".format(
                    city_name, desc, temp, feels, humidity
                )
            )

        except requests.exceptions.Timeout:
            return "Weather service timed out, sir."
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return "I couldn't find weather data for {}, sir.".format(city)
            return "Weather service returned an error, sir."
        except Exception as e:
            print("[WEATHER] Error: {}".format(e))
            return "I was unable to fetch the weather, sir."

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_spotify(self):
        """Lazily initialise SpotifyPlayer when credentials are present."""
        if self._spotify is not None:
            return self._spotify

        client_id     = os.getenv("SPOTIFY_CLIENT_ID", "")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "")
        redirect_uri  = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")
        use_oauth     = os.getenv("SPOTIFY_USE_OAUTH", "false").lower() == "true"

        if not client_id or not client_secret:
            return None

        try:
            self._spotify = SpotifyPlayer(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                use_oauth=use_oauth,
            )
        except Exception as e:
            print("[SPOTIFY] Init error: {}".format(e))
            return None

        return self._spotify
