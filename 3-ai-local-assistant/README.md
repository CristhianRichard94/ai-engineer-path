# JARVIS — AI Local Voice Assistant

A voice-activated personal assistant for Windows. Say "Hey JARVIS" to start a multi-turn conversation session — no wake word needed between commands.

## Pipeline

```
Wake Word → STT (Whisper) → Brain (GPT-4o-mini/4o) → Router → TTS (Fish Speech / pyttsx3)
```

1. **Wake word** — `openwakeword` detects "Hey JARVIS" offline
2. **STT** — mic audio → OpenAI Whisper API
3. **Brain** — GPT-4o-mini classifies intent + params as JSON; escalates to GPT-4o for ambiguous action commands
4. **Router** — dispatches to Windows/API handlers
5. **TTS** — Fish Speech local Docker container (voice cloning); pyttsx3 offline fallback

## What it can do

| Voice command | Intent |
|---|---|
| "Open Chrome" / "Close Spotify" | `open_app` / `close_app` |
| "Search for Python tutorials" | `search_web` |
| "What time is it?" | `get_time` |
| "What's the weather in London?" | `get_weather` |
| "Set volume to 40" | `set_volume` |
| "Open my Documents folder" | `open_folder` |
| "Play Bohemian Rhapsody" | `play_spotify` |
| "Goodbye" | ends session, re-arms wake word |

## Setup

**Prerequisites:** Python 3.10+, Windows 10/11, a microphone, Docker Desktop

```bash
# 1. Create and activate venv
python -m venv venv
venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt
# or double-click install.bat

# 3. Copy and fill in env vars
copy .env.example .env
```

### `.env` keys

```env
OPENAI_API_KEY=
OPENWEATHER_API_KEY=
DEFAULT_CITY=Buenos Aires

# Spotify (optional)
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=http://localhost:8888/callback
SPOTIFY_USE_OAUTH=false          # set true for Premium playback control

# Claude (optional — powers the ask_claude intent's vault-backed SDK path)
ANTHROPIC_API_KEY=
JARVIS_VAULT_DIR=                # override vault location (default: ./vault)
JARVIS_VAULT_TOP_K=4             # number of retrieved vault chunks per ask_claude call
JARVIS_CLAUDE_MODEL=claude-sonnet-5
```

## Voice — Fish Speech Docker container

JARVIS uses [Fish Speech](https://github.com/fishaudio/fish-speech) for voice cloning. It runs locally in a Docker container and requires no cloud API key.

### First-time setup

```bash
# 1. Add your JARVIS reference voice samples (WAV/MP3/FLAC)
#    Place them in tools/voice/references/jarvis/
mkdir tools\voice\references\jarvis
# copy your voice sample(s) here — more samples = better cloning

# 2. Build and start the container
cd tools/voice
docker compose -f docker-compose.jarvis.yml up --build
```

The first run downloads the Fish Speech 1.5 model (~3 GB) from HuggingFace automatically. Subsequent starts are fast — checkpoints are cached at `tools/voice/checkpoints/`.

The API is ready when you see the health check pass:
```
http://localhost:8080/v1/health  →  200 OK
```

### Subsequent starts

```bash
cd tools/voice
docker compose -f docker-compose.jarvis.yml up
```

### How TTS works

- `tts.py` checks `http://localhost:8080/v1/health` at startup
- If the container is running → Fish Speech is used (voice cloning with `references/jarvis/`)
- If the container is down → pyttsx3 offline TTS is used automatically

No config change needed to switch between them — just start or stop the container.

### Reference voice tips

- 5–30 seconds of clean audio is enough
- Less background noise = better quality
- Multiple short clips work better than one long one
- Any format works: WAV, MP3, FLAC

## Run

```bash
# Terminal 1 — voice server (optional but recommended)
cd tools/voice
docker compose -f docker-compose.jarvis.yml up

# Terminal 2 — JARVIS
cd 3-ai-local-assistant
python main.py
```

Say "Hey JARVIS" → JARVIS responds "Yes, sir." → issue commands freely → say "Goodbye" to re-arm.

## Tests

```bash
pytest test/
```

All tests are offline — hardware, network, and audio deps are mocked.

## Project structure

```
jarvis/
  brain.py          # GPT intent classification with mini→4o escalation
  router.py         # intent → Windows/API action dispatcher
  stt.py            # mic capture + Whisper transcription
  tts.py            # Fish Speech primary + pyttsx3 fallback
  wake_word.py      # openwakeword "Hey JARVIS" detection
  spotify_player.py # Spotify search + playback (Client Creds or OAuth)
  constants.py      # JARVIS system prompt + intent schema
main.py             # session loop entry point
test/               # unittest suite (fully mocked)
tools/
  voice/
    docker-compose.jarvis.yml   # Fish Speech container definition
    docker/jarvis-entrypoint.sh # container startup (downloads model + starts server)
    references/jarvis/          # your voice samples go here
    checkpoints/                # model weights cached here after first run
```

## Memory / Vault

JARVIS keeps a local Obsidian-style vault of markdown notes at `vault/` (override
with `JARVIS_VAULT_DIR`), used as retrieval-augmented context for the `ask_claude`
intent:

```
vault/
  prompts/     # auto-generated — one session note per turn, do not edit
  projects/    # hand-written — notes about your projects
  about-me/    # hand-written — personal info (name, role, preferences, current projects)
```

Notes are chunked and embedded locally (`sentence-transformers` + `faiss`, no
cloud calls) into `vault/.index/`. When you ask Claude something via voice, the
most relevant chunks from `vault/projects/` and `vault/about-me/` are retrieved
and passed to Claude as context. The index is rebuilt at JARVIS startup and again
whenever a session ends ("goodbye"), so new session notes become searchable in
the next session.

## Adding a new intent

1. Add intent + params to `JARVIS_SYSTEM` in [`jarvis/constants.py`](jarvis/constants.py)
2. Add handler method to `IntentRouter` in [`jarvis/router.py`](jarvis/router.py)
3. Register in `self._routes` (and `self._DATA_INTENTS` if handler returns the reply string)
4. Add tests in [`test/router.py`](test/router.py)

## Notes

- Mic input uses the OS default recording device (`sd.default.device`) — set your mic as Windows default if wrong device is picked up
- Wake word model (`hey_jarvis_v0.1.onnx`) auto-downloads on first run
- Spotify OAuth mode requires Spotify Premium and stores a cache at `.spotify_cache`
