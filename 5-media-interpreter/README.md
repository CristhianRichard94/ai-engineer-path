# 5-media-interpreter

Transcribe audio, video, or Instagram reels to text — locally (Whisper) or via OpenAI — and interpret a whole video by combining its spoken transcript with an LLM-generated visual description of its frames.

## Setup

```
pip install -r requirements.txt
```

Requires `ffmpeg` on PATH: https://ffmpeg.org/download.html

For `--engine openai` or `--interpret-video`, set `OPENAI_API_KEY`.

## CLI usage

```
python transcribe.py sample.wav                        # audio -> text (local Whisper)
python transcribe.py sample.mp4 --from-video            # video -> extract audio -> text
python transcribe.py sample.mp4 --interpret-video       # video -> transcript + visual description (OpenAI)
python transcribe.py "https://instagram.com/reel/..." --url --from-video
python transcribe.py sample.wav --engine openai         # transcribe via OpenAI instead of local Whisper
```

Flags: `-m/--model` (whisper size), `-l/--language`, `-o/--output`.

## MCP server

Exposes `transcribe_audio`, `extract_audio_from_video`, `interpret_video`, `download_instagram_reel` as MCP tools. `interpret_video` handles the full video-interpretation flow: extracts audio for transcription (OpenAI), samples frames, and sends transcript + frames to `gpt-4o` for a combined summary.

Registered in this repo's root `.mcp.json` as `media-interpreter`:

```json
{
  "mcpServers": {
    "media-interpreter": {
      "command": "python",
      "args": ["5-media-interpreter/mcp_server.py"],
      "cwd": "."
    }
  }
}
```
