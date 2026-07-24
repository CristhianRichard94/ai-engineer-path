# JARVIS MVP — Backlog

Voice-activated local assistant. Status as of this pass.

## Done

- [x] Wake word detection (openwakeword, "Hey JARVIS", continuous bg loop in `main.py`)
- [x] STT (Whisper API capture + transcribe)
- [x] Brain (GPT-4o-mini intent classify, escalate to GPT-4o on ambiguous action commands)
- [x] Router: open_app, close_app, search_web, get_time, get_weather, get_system_info,
      set_volume, open_folder, play_spotify, switch_audio, goodbye, chat
- [x] TTS: Fish Speech (Docker voice clone) -> ElevenLabs -> pyttsx3 fallback chain
- [x] Spotify integration (Client Credentials + optional OAuth/Premium playback)
- [x] Audio output device switcher (nircmd wrapper)
- [x] Multi-turn session loop (wake once, converse until "goodbye")
- [x] Unit tests: brain, router, spotify_player, audio_switcher, tts, wake_word, stt —
      all mocked, 81 passing
- [x] Background/headless launch (`run_background.bat`, pythonw, no console)
- [x] Autostart registered — shortcut in `shell:startup` (`install_autostart.ps1`), points
      at `run_background.bat`

## Fixed this pass (were broken, blocking MVP from running at all)

- [x] `main.py` used flat imports (`from wake_word import ...`) but those modules live in
      `jarvis/`, which was never on `sys.path` — app could not start. Fixed with a
      `sys.path.append(.../jarvis)` in `main.py`.
- [x] `stt.py` picked a mic via `_find_mic()` but then hardcoded `device=15` in the actual
      `sd.rec()` call, ignoring the detected device. Fixed to use `self.device`.
- [x] `switch_audio` intent had a full implementation (`audio_switcher.py`) and a full test
      suite (`test/router.py::TestSwitchAudio`) but was never wired into `IntentRouter` or
      `constants.py`'s intent schema — GPT could never emit it. Wired in.
- [x] `spotify_player._play_via_uri` called `os.startfile()` first, which on a real Windows
      test run launches the actual Spotify app as a side effect and never matched what the
      tests (and the non-Windows fallback) expected. Simplified to always use
      `subprocess.Popen`.
- [x] `spotify_player._search_track` crashed with `AttributeError` on any generic exception
      without an `http_status` attribute. Fixed with `getattr(e, "http_status", None)`.

## Remaining gaps (not done)

- [ ] Mic device selection relies on matching `'Realtek'` in device name — hardcoded to the
      dev machine's hardware, silently falls back to system default elsewhere. Fine for
      personal use, brittle if shared/deployed.
- [ ] No error recovery if the Fish Speech Docker container dies mid-session (falls back
      per-call, but no reconnect/backoff logic).
- [ ] No wake-word sensitivity/threshold tuning UI — `threshold = 0.3` is a fixed constant.
- [x] No conversation memory persistence across process restarts — addressed via a
      local Obsidian-style vault (`jarvis/vault.py`) + FAISS retrieval: every turn
      is written as a session note under `vault/prompts/`, and `ask_claude`
      retrieves relevant chunks from the vault (session notes + hand-written
      `vault/projects/` and `vault/about-me/` notes) as context for the Anthropic
      SDK call in `jarvis/claude_client.py`. Note: `JarvisBrain.history` itself is
      still in-RAM per-session (cleared on restart/"New Conversation") — the vault
      gives cross-session *recall via retrieval*, not literal history replay.

## Conversation-flow gaps (found via OpenJarvis comparison, 2026-07-24)

- [x] No text chat endpoint exists at all — fixed: `POST /chat` in `ui/server.py`, reuses
      `JarvisBrain`/`IntentRouter` under a lock, writes transcript + vault note. Merged
      `feature/text-chat` (2026-07-24), QA + security clean both rounds.
- [ ] Intent routing and conversational reply are the same call — `brain.py:_call_model`
      does JSON-mode intent classification, and `chat` intent's `reply` field IS the
      conversational answer (`router.py` routes `chat` -> `do_nothing`, just echoes it).
      No dedicated multi-turn chat completion path. Fragile for genuine back-and-forth.
      Deliberately deferred: splitting this is a model-behavior/cost tradeoff call, not a
      bug — current single-call approach works fine in practice. Revisit if chat replies
      start feeling shallow, not preemptively.
- [x] `brain.history` had no session/conversation id, making it impossible to tell which
      process lifetime a transcript entry belongs to. Fixed: `JarvisBrain.conversation_id`
      (uuid4, regenerated on init and on history reset), threaded through
      `append_transcript(role, text, conversation_id)` into `transcript.jsonl`, and
      surfaced from `ui/server.py` via `GET /state`'s `conversation_id` field. History
      itself is still in-RAM per-process (unchanged) — this only makes restarts/resets
      visible/attributable in the transcript, it does not add persistence or resumption.
- [ ] Reset is all-or-nothing: UI "New Conversation" wipes `brain.history = []` entirely
      (`ui/server.py` reset signal -> `main.py`) — no per-conversation scoping, can't run
      two independent conversations or resume a specific one. Deliberately deferred:
      this app is single-user/single-active-conversation by design (one voice loop, one
      chat UI) — true multi-session resume needs a session store, a real new feature, not
      a gap-fill. Revisit only if multi-conversation becomes an actual ask.
- [x] No frontend chat UI — fixed alongside the `/chat` endpoint: `ChatInput.tsx` wired
      into `App.tsx` below the transcript panel. Merged `feature/text-chat` (2026-07-24).

## Cleaned up this pass

- [x] Deleted stale `jarvis/tts.py` duplicate (dead file, root `tts.py` was already the one
      actually imported).
