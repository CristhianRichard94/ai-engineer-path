# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all tests
pytest test/

# Run a single test file
pytest test/brain.py
pytest test/router.py

# Run a single test by name
pytest test/brain.py::JarvisBrainTests::test_think_escalates_when_fallback_intent_and_action_keyword

# Start the assistant
python main.py

# Install dependencies (uses project venv)
pip install -r requirements.txt
```

## Required `.env` keys

```
OPENAI_API_KEY=
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
OPENWEATHER_API_KEY=
DEFAULT_CITY=Buenos Aires
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=http://localhost:8888/callback
SPOTIFY_USE_OAUTH=false
AUDIO_DEVICE_SPEAKER=<exact Windows device name>
AUDIO_DEVICE_HEADPHONES=<exact Windows device name>
NIRCMD_PATH=                  # optional, defaults to switch-audio-output/nircmd.exe
```

## Architecture

**Pipeline (main.py):** `WakeWord → STT → Brain → Router → TTS`

Single session loop: detect "Hey JARVIS" wake word → multi-turn conversation (no wake word needed between turns) → `goodbye` intent ends the session and re-arms wake word.

**Brain (`brain.py` / `constants.py`):** `JarvisBrain` sends user text to `gpt-4o-mini` with a strict JSON schema (`{intent, params, reply}`). If the returned intent is in `FALLBACK_INTENTS` (just `"chat"`) **and** the raw text contains action keywords, it escalates to `gpt-4o` for one call. `JARVIS_SYSTEM` in `constants.py` is the system prompt — it defines every legal intent and its params schema.

**Router (`router.py`):** `IntentRouter.dispatch()` looks up the intent in `_routes` (a name→method-name dict, not bound methods, so tests can monkey-patch via attribute assignment). Intents in `_DATA_INTENTS` have handlers that return the spoken reply; all other intents execute a side-effect and the brain's `reply` field is spoken.

**TTS (`tts.py`):** ElevenLabs primary (`pcm_22050` format, played via `sounddevice`), pyttsx3 offline fallback. pyttsx3 is confined to a single daemon thread because SAPI5 is not thread-safe.

**STT (`stt.py`):** Records at 48 kHz (Realtek hardware rate), resamples 3× down to 16 kHz via `resample_poly`, sends WAV to Whisper API. Device index 15 is hardcoded in `capture_and_transcribe` — change this if mic index differs.

**Wake word (`wake_word.py`):** Uses `openwakeword` with a `hey_jarvis_v0.1.onnx` model auto-downloaded on first run from GitHub. Captures at 48 kHz in 80 ms chunks and resamples to 16 kHz before inference.

**Audio switching (`audio_switcher.py`):** Wraps `nircmd.exe` (bundled in `switch-audio-output/`). Device names must exactly match Windows Sound control panel strings, configured via `.env`.

**Spotify (`spotify_player.py`):** Two modes — Client Credentials (search + URI launch, no Premium) and OAuth (full playback API, Premium required, set `SPOTIFY_USE_OAUTH=true`). OAuth cache stored at `.spotify_cache` in project root.

## Test patterns

Tests in `test/` use `unittest`. No real hardware or network needed — all external deps (`openai`, `psutil`, `subprocess`, `requests`, `pycaw`, `spotipy`, `AudioSwitcher`) are mocked. Test files add the project root to `sys.path` manually so they run from the `test/` directory. The `_make_router()` helper in `test/router.py` is the canonical way to get a patched `IntentRouter`.

## Adding a new intent

1. Add the intent + params schema to `JARVIS_SYSTEM` in `constants.py`
2. Add a handler method to `IntentRouter` in `router.py`
3. Register it in `self._routes` (and `self._DATA_INTENTS` if the handler returns the spoken reply)
4. Add tests in `test/router.py`
