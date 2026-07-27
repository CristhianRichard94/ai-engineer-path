"""
router.py - Intent dispatcher for JARVIS.

Maps intent names (from brain.py) to concrete Windows/API actions.
"""

import json
import os
import re
import shutil
import subprocess
import time
import webbrowser
from datetime import datetime

import psutil
import requests

from spotify_player import SpotifyPlayer, SpotifyAuthError
from audio_switcher import AudioSwitcher
from state import append_claude_audit
from vault import retrieve
from claude_client import ClaudeClient
import project_tracker_mcp


class IntentRouter:
    # How long a pending slot-fill/confirmation stays "live" before it's
    # treated as abandoned. Over voice this is effectively moot (tight
    # turn-taking), but over HTTP chat a user can leave a clarifying
    # question unanswered indefinitely; without a TTL, a later unrelated
    # message would get silently misinterpreted as the answer to a stale
    # pending slot.
    _PENDING_TTL_SECONDS = 120

    def __init__(self):
        self.weather_key  = os.getenv("OPENWEATHER_API_KEY")
        self.default_city = os.getenv("DEFAULT_CITY", "Buenos Aires")

        # Spotify player (lazy-loaded on first use)
        self._spotify = None
        self._audio   = AudioSwitcher()

        # Anthropic SDK client for the vault-backed ask_claude path (only
        # configured if an API key is present in the environment).
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self._claude = ClaudeClient(anthropic_key) if anthropic_key else None

        # Single-slot pending-clarification state (documented limitation:
        # only one outstanding slot-fill conversation at a time, no
        # generic intent-interruption support).
        self._pending = None

        # Descriptions of tasks from the most recent successful
        # daily_task_reminder listing, in listed order - lets manage_task
        # resolve ordinal/pronoun references ("the first one", "that one")
        # without the user having to repeat the task text.
        # TODO: no TTL/clear-on-New-Conversation for this list (unlike
        # self._pending's 120s TTL) - acceptable for now since the
        # confirm-gate names the resolved task before acting, but worth
        # revisiting if it starts serving stale matches.
        self._last_tasks = []

        # The *effective* intent for the turn just dispatched - i.e. what
        # the router actually did, not necessarily what brain.think() raw-
        # classified the turn's text as. When a turn resolves a pending
        # confirmation (e.g. "yes" answering a daily_task_reminder_confirm
        # or manage_task_confirm prompt), the effective intent is the
        # domain intent the conversation is still in (so sticky routing in
        # brain.py survives a bare confirm turn), not "chat". Callers
        # (main.py, ui/server.py) should read this right after dispatch()
        # and use it to update brain.last_intent instead of trusting
        # brain.think()'s own classification of the confirm utterance.
        self.last_effective_intent = None

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
            "manage_task"    : "manage_task",
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
            "manage_task",
        }

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def _set_pending(self, pending):
        """Set self._pending, stamping it with the current time so dispatch()
        can expire it via _PENDING_TTL_SECONDS."""
        pending["_ts"] = time.monotonic()
        self._pending = pending

    def dispatch(self, parsed, raw_text=None):
        # A prior turn left a slot unfilled (e.g. "play spotify" with no
        # query, or the new_project wizard mid-flow) -> this turn's parsed
        # params are treated as the answer to that slot, not a fresh intent.
        if self._pending is not None:
            age = time.monotonic() - self._pending.get("_ts", 0)
            if age > self._PENDING_TTL_SECONDS:
                # Stale clarification - drop it and process this turn as a
                # fresh intent instead of silently misinterpreting it as the
                # answer to a question the user has moved on from.
                self._pending = None
            else:
                reply = self._continue_pending(parsed, raw_text)
                # _continue_pending() already set self.last_effective_intent
                # for the pending intent it resolved.
                return reply

        intent = parsed.get("intent", "chat")
        params = parsed.get("params", {})
        reply  = parsed.get("reply", "Done, sir.")

        method_name = self._routes.get(intent, "do_nothing")
        fn = getattr(self, method_name, self.do_nothing)

        self.last_effective_intent = intent

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
            self.last_effective_intent = "switch_audio"
            device = (parsed.get("params", {}) or {}).get("device", "").strip()
            if not device:
                device = (raw_text or "").strip()
            self._pending = None
            if not device:
                return "I still didn't catch the audio device, sir. Let's try again."
            return self.switch_audio({"device": device})

        if intent == "play_spotify":
            self.last_effective_intent = "play_spotify"
            query = (parsed.get("params", {}) or {}).get("query", "").strip()
            if not query:
                query = (raw_text or "").strip()
            self._pending = None
            if not query:
                return "I still didn't catch what to play, sir. Let's try again."
            return self.play_spotify({"query": query})

        if intent == "ask_claude":
            self.last_effective_intent = "ask_claude"
            query = (parsed.get("params", {}) or {}).get("query", "").strip()
            if not query:
                query = (raw_text or "").strip()
            self._pending = None
            if not query:
                return "I still didn't catch the question, sir. Let's try again."
            return self.ask_claude({"query": query})

        if intent == "ask_claude_confirm":
            self.last_effective_intent = "ask_claude"
            query = pending["query"]
            self._pending = None
            if self._is_affirmative(parsed, raw_text):
                return self._ask_claude_sdk(query)
            return "Okay, cancelled, sir."

        if intent == "daily_task_reminder_confirm":
            # Effective intent stays in the task domain (not "chat") so
            # that sticky routing in brain.py survives this bare confirm
            # turn and the *next* turn (e.g. "mark the first one done")
            # still gets escalated/routed correctly.
            self.last_effective_intent = "daily_task_reminder"
            self._pending = None
            if self._is_affirmative(parsed, raw_text):
                return self._daily_task_reminder_reply()
            return "Okay, cancelled, sir."

        if intent == "manage_task_confirm":
            # Same reasoning as daily_task_reminder_confirm above.
            self.last_effective_intent = "manage_task"
            self._pending = None
            if self._is_affirmative(parsed, raw_text):
                return self._manage_task_execute(pending)
            return "Okay, cancelled, sir."

        if intent == "new_project":
            self.last_effective_intent = "new_project"
            return self._advance_new_project(parsed, raw_text)

        # Unknown pending intent — clear it defensively rather than get stuck.
        self.last_effective_intent = "chat"
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
        # List-form argv (no shell=True) — `exe` ultimately originates from
        # GPT's intent-classification of user-controlled text (voice
        # transcript / /chat message), so it must never be interpolated
        # into a shell command string. CreateProcess still does a PATH
        # search for a bare executable name (e.g. "notepad.exe") in list
        # form on Windows, so this is not relying on shell built-ins.
        # shell=True used to expand %USERNAME%-style env vars via cmd.exe;
        # list-form Popen skips that, so expand them ourselves first.
        exe = os.path.expandvars(exe)
        subprocess.Popen([exe])

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
        # List-form argv (no shell string interpolation) — avoids shell
        # metacharacter injection from a path containing e.g. `"`, `&`, `|`,
        # since `p["path"]` ultimately originates from user-controlled text.
        subprocess.Popen(["explorer", p["path"]])

    def play_spotify(self, p):
        query = p.get("query", "").strip()
        if not query:
            self._set_pending({"intent": "play_spotify"})
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
            self._set_pending({"intent": "switch_audio"})
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
            self._set_pending({"intent": "ask_claude"})
            return "What would you like to ask Claude, sir?"
        # Confirmation gate: the query comes from voice/ambient audio -> STT
        # -> intent parser -> straight into an agentic CLI with real
        # file-system access. Never dispatch without an explicit "yes".
        self._set_pending({"intent": "ask_claude_confirm", "query": query})
        return "You want me to ask Claude: '{}'. Say yes to confirm, sir.".format(query)

    def daily_task_reminder(self, p):
        # Same confirmation gate as ask_claude - this also invokes the
        # agentic CLI (with project-tracker MCP tool access).
        self._set_pending({"intent": "daily_task_reminder_confirm"})
        return "Want me to check today's tasks with Claude, sir? Say yes to confirm."

    def _daily_task_reminder_reply(self):
        """Fetch open tasks via a direct MCP call to the project-tracker
        server (bypassing the Claude Code CLI for this one skill) and
        summarize them into a spoken reply.

        On any MCP-level failure (missing node, server crash, timeout),
        falls back to the existing `_call_claude_cli` path so the user
        isn't left with nothing. On the CLI-fallback path, self._last_tasks
        is left unchanged (the CLI path doesn't yield a clean parseable
        list, don't guess).
        """
        try:
            raw_tasks = project_tracker_mcp.call_tool("list_open_tasks")
        except project_tracker_mcp.ProjectTrackerMCPError as e:
            print("[PROJECT_TRACKER_MCP] Direct call failed, falling back "
                  "to Claude CLI: {}".format(e))
            return self._call_claude_cli(
                self._DAILY_TASK_PROMPT,
                allowed_tools=["mcp__project-tracker__list_open_tasks"],
            )

        descriptions = self._parse_open_tasks(raw_tasks)
        # Only overwrite _last_tasks on a real, successfully-parsed listing
        # (including the legitimate "zero open tasks" case) so a later
        # failed re-listing doesn't wipe out a still-valid prior list.
        self._last_tasks = descriptions
        return self._summarize_open_tasks(raw_tasks, descriptions)

    # Matches the numbered task lines the project-tracker MCP server emits,
    # e.g. "    3. Fix the login bug (created 2026-07-20)" — everything else
    # in its list_open_tasks text (section/priority headers) is layout, not
    # a task, so it's skipped when building the spoken summary.
    _TASK_LINE_RE = re.compile(r"^\s*\d+\.\s*(.+?)\s*\(created\s+[^)]*\)\s*$")

    @classmethod
    def _parse_open_tasks(cls, raw_tasks):
        """Extract the ordered list of task descriptions from the raw
        list_open_tasks tool text (empty list if none/unparseable)."""
        text = (raw_tasks or "").strip()
        if not text or text.lower() == "no open tasks.":
            return []

        descriptions = []
        for line in text.splitlines():
            match = cls._TASK_LINE_RE.match(line)
            if match:
                descriptions.append(match.group(1).strip())
        return descriptions

    @classmethod
    def _summarize_open_tasks(cls, raw_tasks, descriptions=None):
        """Turn the raw list_open_tasks tool text into a speech-friendly
        reply, without needing a further round-trip to an LLM."""
        text = (raw_tasks or "").strip()
        if not text or text.lower() == "no open tasks.":
            return "You have no open tasks, sir."

        if descriptions is None:
            descriptions = cls._parse_open_tasks(raw_tasks)

        if not descriptions:
            # Non-empty tool output that didn't match a single task line -
            # likely the server's output format drifted from _TASK_LINE_RE.
            # Log it rather than silently telling the user "no open tasks"
            # when tasks may actually exist.
            print("[PROJECT_TRACKER_MCP] list_open_tasks returned non-empty "
                  "text but no task line matched _TASK_LINE_RE: {!r}".format(text))
            return "You have no open tasks, sir."

        if len(descriptions) == 1:
            return "You have one open task, sir: {}.".format(descriptions[0])

        return "You have {} open tasks, sir: {}.".format(
            len(descriptions), "; ".join(descriptions)
        )

    # Ordinal/pronoun words that can stand in for an item from the most
    # recently spoken task list, and the index they resolve to.
    _ORDINAL_INDEX = {
        "first": 0, "1st": 0,
        "second": 1, "2nd": 1,
        "third": 2, "3rd": 2,
        "last": -1,
    }
    _PRONOUN_WORDS = {"that", "that one", "it"}

    # Regex-free normalization for ordinal/pronoun phrasing: strips a
    # leading "the " and a trailing " one" (case-insensitive) so that
    # "the first one" / "the last one" — the exact phrasing constants.py's
    # JARVIS_SYSTEM prompt documents as a valid model output — match
    # _ORDINAL_INDEX/_PRONOUN_WORDS the same way bare "first"/"last" do.
    @staticmethod
    def _normalize_reference_key(text):
        key = (text or "").strip().lower()
        if key.startswith("the "):
            key = key[len("the "):]
        if key.endswith(" one") and key != "one":
            key = key[: -len(" one")]
        return key.strip()

    def manage_task(self, p):
        p = p or {}
        action = (p.get("action") or "").strip().lower()
        query = (p.get("query") or "").strip()
        description = (p.get("description") or "").strip()
        priority = p.get("priority")

        if action not in ("done", "delete", "add", "edit"):
            return "I'm not sure what task change you mean, sir."

        # "add" doesn't need a query - it's built purely from description.
        if action != "add":
            original_key = self._normalize_reference_key(query)
            is_reference = (
                original_key in self._ORDINAL_INDEX
                or original_key in self._PRONOUN_WORDS
            )

            resolved_query, error = self._resolve_task_reference(query)
            if error:
                return error
            query = resolved_query

            # Ordinal/pronoun references above already resolved to a real
            # task description straight out of self._last_tasks. A direct
            # text query (e.g. "spotify") hasn't been checked against the
            # real task list yet — resolve it now so the spoken
            # confirmation names the task the MCP server's own fuzzy
            # matcher will actually act on, not the user's raw search
            # text. Without this, a reflexive "yes" could confirm against
            # a match the user never saw and never actually intended.
            if not is_reference:
                matched_query, match_error = self._resolve_direct_query(query)
                if match_error:
                    return match_error
                query = matched_query

        if action == "add" and not description:
            return "What should the new task say, sir?"

        pending = {
            "intent": "manage_task_confirm",
            "action": action,
            "query": query,
            "description": description,
            "priority": priority,
        }
        self._set_pending(pending)

        if action == "done":
            return "You want me to mark '{}' done, sir? Say yes to confirm.".format(query)
        if action == "delete":
            return "You want me to delete '{}', sir? Say yes to confirm.".format(query)
        if action == "add":
            return "You want me to add a task: '{}', sir? Say yes to confirm.".format(description)
        # edit
        return "You want me to update '{}', sir? Say yes to confirm.".format(query)

    def _resolve_task_reference(self, query):
        """Resolve an ordinal/pronoun reference against self._last_tasks.

        Returns (resolved_query, error). If query isn't a reference word (or
        is empty), it's passed through unchanged with error=None. If it is a
        reference word but can't be resolved, resolved_query is None and
        error is a clarifying reply to speak (no MCP call should follow).
        """
        key = self._normalize_reference_key(query)
        if key not in self._ORDINAL_INDEX and key not in self._PRONOUN_WORDS:
            return query, None

        if not self._last_tasks:
            return None, "Which task do you mean, sir? I don't have a recent list to go by."

        if key in self._PRONOUN_WORDS:
            if len(self._last_tasks) == 1:
                return self._last_tasks[0], None
            return None, "Which task do you mean, sir? I don't have a recent list to go by."

        index = self._ORDINAL_INDEX[key]
        try:
            return self._last_tasks[index], None
        except IndexError:
            return None, "Which task do you mean, sir? I don't have a recent list to go by."

    def _resolve_direct_query(self, query):
        """Resolve a direct-text task query (e.g. "spotify") against the
        real open-task list before it's used in a spoken confirmation
        prompt, so the confirmation names the task that will actually be
        matched/mutated server-side - not the user's raw (possibly
        ambiguous or simply wrong) search text.

        Uses self._last_tasks if populated (from a recent listing),
        falling back to a fresh list_open_tasks MCP call if it's empty or
        stale. Matching is a simple case-insensitive substring check -
        good enough to name a real candidate, not a reimplementation of
        the MCP server's own fuzzy matcher.

        Returns (matched_query, error). On exactly one match, returns the
        real task description with error=None. On zero or multiple
        matches (or if the task list can't be fetched at all), returns
        (None, clarifying reply) so the caller does not proceed to set a
        misleading confirmation.
        """
        tasks = self._last_tasks
        if not tasks:
            try:
                raw_tasks = project_tracker_mcp.call_tool("list_open_tasks")
            except project_tracker_mcp.ProjectTrackerMCPError as e:
                print("[PROJECT_TRACKER_MCP] Direct call failed while "
                      "resolving task reference: {}".format(e))
                return None, "I couldn't find a task matching '{}', sir.".format(query)
            tasks = self._parse_open_tasks(raw_tasks)
            self._last_tasks = tasks

        needle = query.lower().strip()
        matches = [t for t in tasks if needle and needle in t.lower()]

        if not matches:
            return None, "I couldn't find a task matching '{}', sir.".format(query)
        if len(matches) > 1:
            return None, (
                "I found more than one task matching '{}', sir - "
                "which one do you mean?".format(query)
            )
        return matches[0], None

    _MANAGE_TASK_TOOL_NAMES = {
        "done"  : "mark_task_done",
        "delete": "delete_task",
        "add"   : "add_task",
        "edit"  : "edit_task",
    }

    def _manage_task_execute(self, pending):
        """Execute a confirmed manage_task action via a direct MCP call to
        the project-tracker server, falling back to the Claude Code CLI on
        any MCP-level failure - same pattern as _daily_task_reminder_reply.
        """
        action = pending.get("action")
        query = pending.get("query", "")
        description = pending.get("description", "")
        priority = pending.get("priority")

        tool_name = self._MANAGE_TASK_TOOL_NAMES.get(action)
        if tool_name is None:
            return "I'm not sure what task change you mean, sir."

        arguments = {}
        if action == "done":
            arguments = {"query": query}
        elif action == "delete":
            arguments = {"query": query}
        elif action == "add":
            arguments = {"description": description}
            if priority is not None:
                arguments["priority"] = priority
        elif action == "edit":
            arguments = {"query": query}
            if description:
                arguments["description"] = description
            if priority is not None:
                arguments["priority"] = priority

        prompt = self._manage_task_cli_prompt(action, query, description, priority)

        try:
            result = project_tracker_mcp.call_tool(tool_name, arguments)
        except project_tracker_mcp.ProjectTrackerMCPError as e:
            print("[PROJECT_TRACKER_MCP] Direct call failed, falling back "
                  "to Claude CLI: {}".format(e))
            return self._call_claude_cli(
                prompt,
                allowed_tools=["mcp__project-tracker__{}".format(tool_name)],
            )

        return result or "Done, sir."

    @staticmethod
    def _manage_task_cli_prompt(action, query, description, priority):
        """Build the one-shot CLI fallback prompt for a manage_task action."""
        if action == "done":
            return (
                "Use the mcp__project-tracker__mark_task_done tool to mark the task "
                "matching '{}' as done. Report the result as your final answer — "
                "this is a one-shot request, don't wait for further input.".format(query)
            )
        if action == "delete":
            return (
                "Use the mcp__project-tracker__delete_task tool to delete the task "
                "matching '{}'. Report the result as your final answer — this is a "
                "one-shot request, don't wait for further input.".format(query)
            )
        if action == "add":
            extra = " with priority {}".format(priority) if priority is not None else ""
            return (
                "Use the mcp__project-tracker__add_task tool to add a new task: "
                "'{}'{}. Report the result as your final answer — this is a one-shot "
                "request, don't wait for further input.".format(description, extra)
            )
        # edit
        parts = []
        if description:
            parts.append("description to '{}'".format(description))
        if priority is not None:
            parts.append("priority to {}".format(priority))
        change = " and ".join(parts) if parts else "its details"
        return (
            "Use the mcp__project-tracker__edit_task tool to update the task matching "
            "'{}', setting its {}. Report the result as your final answer — this is a "
            "one-shot request, don't wait for further input.".format(query, change)
        )

    def _ask_claude_sdk(self, query):
        """Answer `query` via the Anthropic SDK, augmented with vault
        context retrieved via FAISS. Used by ask_claude_confirm - the
        MCP-tool-driven daily_task_reminder path still uses _call_claude_cli.
        """
        if self._claude is None:
            # No ANTHROPIC_API_KEY -> fall back to the Claude Code CLI
            # (same path daily_task_reminder uses), so ask_claude still
            # works via whatever `claude` is already logged into, with
            # project-tracker MCP access for task-related questions.
            return self._call_claude_cli(
                query, allowed_tools=["mcp__project-tracker__list_open_tasks"]
            )

        top_k = int(os.getenv("JARVIS_VAULT_TOP_K", "4"))
        chunks = retrieve(query, top_k=top_k)

        model = os.getenv("JARVIS_CLAUDE_MODEL", "claude-sonnet-5")
        reply, error = self._claude.ask(query, chunks, model=model)

        if error:
            append_claude_audit(query, reply, error, None)
        else:
            append_claude_audit(query, reply, "", 0)

        if reply and len(reply) > self._CLAUDE_REPLY_LIMIT:
            reply = reply[:self._CLAUDE_REPLY_LIMIT].rstrip() + "...(truncated)"

        return reply

    def _call_claude_cli(self, prompt, allowed_tools=None):
        """Run the Claude Code CLI non-interactively and return a spoken reply.

        List-form argv (no shell=True) — the prompt is passed as a single
        argument, so there is no shell-injection risk regardless of content.

        Runs in `--permission-mode plan` (read-only planning, no file/tool
        mutations) rather than trusting the user's ambient global Claude
        Code permission config, since this call path is triggered by
        unattended voice/ambient audio. Plan mode never *executes* tools at
        all though - it only plans - so callers that pass `allowed_tools`
        (meaning they need that tool to actually run, e.g.
        daily_task_reminder's project-tracker read tool) get `default` mode
        instead, scoped tightly via --allowedTools to just those tools.
        Every invocation is recorded, full and untruncated, to
        claude_cli_audit.jsonl via state.append_claude_audit for
        after-the-fact review.
        """
        if not shutil.which("claude"):
            return "Claude Code isn't installed, sir."

        # "plan" mode never executes tools, only plans - useless for a
        # caller that actually needs a tool's result (e.g. the todo list).
        # "default" + a tight --allowedTools scope lets exactly those tools
        # run without opening up file/shell mutations generally.
        mode = "default" if allowed_tools else "plan"
        cmd = ["claude", "-p", prompt, "--permission-mode", mode]
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
        self._set_pending({
            "intent": "new_project",
            "step": None,
            "name": name,
            "description": description,
        })
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
