# 5-media-interpreter

Turn audio, video, or Instagram reels into text and structured summaries — locally (Whisper) or via OpenAI.

## What it does

- **Transcribe audio** to text, using either a local Whisper model or the OpenAI transcription API.
- **Transcribe video** by first extracting its audio track (ffmpeg), then transcribing that.
- **Interpret a whole video**: combines the spoken transcript with an LLM-generated visual description of sampled frames into one coherent summary (`gpt-4o`, requires `OPENAI_API_KEY`).
- **Download Instagram reels** (via `yt-dlp`) so they can be fed into any of the above.

All of this is available both as a CLI (`transcribe.py`) and as an MCP server (`mcp_server.py`) that exposes the same capabilities as tools for MCP clients (e.g. Claude Code).

## Architecture notes (MCP security)

The MCP server is designed to be safely callable by an untrusted or semi-trusted MCP client (an LLM acting on the client's behalf), which means every tool input is treated as adversarial:

- **Workspace confinement.** Every MCP tool that takes a file path (`transcribe_audio`, `extract_audio_from_video`, `interpret_video`) resolves it inside a single, dedicated directory: `~/.media-interpreter/workspace`. Inputs must be relative, must not contain a URI scheme (`://`), and must not resolve outside that root (e.g. via `..`) — `_resolve_in_workspace()` enforces this. This prevents a malicious or confused client from reading/writing arbitrary files on the host by supplying an absolute path or a path-traversal string. Tool outputs are likewise returned as paths relative to the workspace, and error messages strip out the real resolved absolute path so a client can't use error text to map the host filesystem.
- **Instagram URL host allow-list.** `download_instagram_reel` only accepts `http(s)` URLs whose host is exactly one of `instagram.com`, `www.instagram.com`, `vm.instagram.com` (mobile share-sheet short links), or `instagr.am` (legacy short domain). This stops the tool from being used as a generic SSRF/download proxy for arbitrary URLs — `yt-dlp` supports hundreds of sites, and without this check the tool would happily fetch from any of them on a client's behalf.

Both checks are deliberately narrow allow-lists (exact host match after stripping credentials/port), not blocklists, since blocklists are easy to bypass.

## Setup

```
pip install -r requirements.txt
```

Requires `ffmpeg` (and `ffprobe`, which ships with it) on `PATH`: https://ffmpeg.org/download.html

For `--engine openai`, `--interpret-video`, or the MCP `interpret_video`/OpenAI-engine tools, set `OPENAI_API_KEY` as an environment variable (never hardcode it):

```
export OPENAI_API_KEY=sk-...
```

## CLI usage

```
python transcribe.py sample.wav                        # audio -> text (local Whisper)
python transcribe.py sample.mp4 --from-video            # video -> extract audio -> text
python transcribe.py sample.mp4 --interpret-video       # video -> transcript + visual description (OpenAI)
python transcribe.py "https://instagram.com/reel/..." --url --from-video
python transcribe.py sample.wav --engine openai         # transcribe via OpenAI instead of local Whisper
```

Flags:

| Flag | Description |
|---|---|
| `input` | Audio file, video file, or Instagram reel URL (positional) |
| `--url` | Treat `input` as an Instagram reel URL to download first |
| `--from-video` | Extract audio from a video input, then transcribe |
| `--interpret-video` | Whole-video LLM interpretation (transcript + visual description); implies OpenAI |
| `--engine {whisper,openai}` | Transcription engine (default: `whisper`) |
| `-m/--model {tiny,base,small,medium,large}` | Whisper model size (default: `base`) |
| `-l/--language` | Language hint, e.g. `en`, `es` (default: auto-detect) |
| `-o/--output` | Write the result to this `.txt` path instead of stdout |

## MCP server

Exposes four tools:

| Tool | Params | Returns |
|---|---|---|
| `transcribe_audio` | `audio_path: str`, `engine: str = "whisper"`, `model: str = "base"`, `language: str \| None = None` | Transcript text |
| `extract_audio_from_video` | `video_path: str` | Relative path to the extracted `.wav` |
| `interpret_video` | `video_path: str`, `prompt: str \| None = None` | Combined transcript + visual summary |
| `download_instagram_reel` | `url: str` | Relative path to the downloaded video file |

All `*_path` parameters must be **relative paths inside the workspace** (see Architecture notes above) — pass back the relative path a previous tool call returned, not an absolute path.

Registered in this repo's root `.mcp.json` as `media-interpreter`:

```json
{
  "mcpServers": {
    "media-interpreter": {
      "type": "stdio",
      "command": "python",
      "args": ["5-media-interpreter/mcp_server.py"],
      "cwd": "."
    }
  }
}
```

### Example: download a reel, then transcribe it

An MCP client should chain the tools by feeding one tool's returned relative path into the next:

1. Call `download_instagram_reel(url="https://vm.instagram.com/abc123")`.
   → Returns e.g. `"a1b2c3d4e5f6.../abc123.mp4"` (relative to the workspace).
2. Call `extract_audio_from_video(video_path="a1b2c3d4e5f6.../abc123.mp4")`.
   → Returns e.g. `"a1b2c3d4e5f6.../abc123.wav"`.
3. Call `transcribe_audio(audio_path="a1b2c3d4e5f6.../abc123.wav", engine="whisper")`.
   → Returns the transcript text.

(Alternatively, skip steps 2–3 and call `interpret_video(video_path="a1b2c3d4e5f6.../abc123.mp4")` directly for a combined transcript + visual summary.)

## Limitations / known gaps

- `interpret_video` always transcribes via the OpenAI API (not local Whisper) and always uses `gpt-4o` — neither is currently configurable.
- Frame sampling in `_extract_frames` targets a fixed count (6) spread evenly across the video's duration; there's no scene-detection or keyframe selection.
- `download_instagram_reel` relies on `yt-dlp`, which regularly needs updating as Instagram changes its site internals (see the pin note in `requirements.txt`); a stale pin can start failing downloads even though nothing in this repo changed.
- No automatic cleanup of `~/.media-interpreter/workspace` — files accumulate there across MCP sessions and must be pruned manually if disk usage matters.
- No file-size/duration limits are enforced before processing, so a very large input can be slow or memory-heavy (frame extraction/base64-encoding in particular).

## Troubleshooting

- **`ffmpeg not found on PATH`**: install ffmpeg (https://ffmpeg.org/download.html) and confirm `ffmpeg -version` works from the same shell you're running this from.
- **`OPENAI_API_KEY env var not set`**: export the variable in your shell (or `.env`, loaded by your process manager) before using `--engine openai`, `--interpret-video`, or the equivalent MCP tools.
- **`URL host is not an allowed Instagram host`**: only `instagram.com`, `www.instagram.com`, `vm.instagram.com`, and `instagr.am` links are accepted; resolve redirects/shorteners to one of these first.
- **`Path escapes the workspace` / `Absolute paths are not allowed`**: MCP tool paths must be relative paths previously returned by another tool call in this session, not arbitrary filesystem paths.
