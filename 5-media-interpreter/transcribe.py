#!/usr/bin/env python3
"""Transcribe audio/video to text, locally (Whisper) or via OpenAI."""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import whisper

if TYPE_CHECKING:
    from openai import OpenAI


def _require_ffmpeg() -> None:
    """Raise RuntimeError if the ffmpeg binary is not available on PATH."""
    from shutil import which
    if which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found on PATH. Install it: https://ffmpeg.org/download.html")


def _require_openai() -> "OpenAI":
    """Return an authenticated OpenAI client, or raise RuntimeError if
    OPENAI_API_KEY is not set."""
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY env var not set.")
    from openai import OpenAI
    return OpenAI()


def extract_audio_from_video(video_path: Path, out_path: Path | None = None) -> Path:
    """Extract the audio track from video_path as 16-bit PCM WAV via ffmpeg.

    Returns the path to the resulting .wav file (out_path, or video_path with
    its suffix swapped to .wav if out_path is not given).
    """
    _require_ffmpeg()
    video_path = Path(video_path)
    out_path = Path(out_path) if out_path else video_path.with_suffix(".wav")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-acodec", "pcm_s16le", str(out_path)],
        check=True, capture_output=True,
    )
    return out_path


def download_instagram_reel(url: str, out_dir: Path) -> Path:
    """Download an Instagram reel from url into out_dir via yt-dlp.

    Returns the local path to the downloaded video file.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(out_dir / "%(id)s.%(ext)s")
    import yt_dlp
    with yt_dlp.YoutubeDL({"outtmpl": out_template, "format": "mp4/best"}) as ydl:
        info = ydl.extract_info(url, download=True)
        path = ydl.prepare_filename(info)
    return Path(path)


def transcribe_audio(audio_path: Path, engine: str = "whisper",
                      model: str = "base", language: str | None = None) -> str:
    """Transcribe an audio file to text.

    engine: "whisper" runs a local Whisper model of the given size; "openai"
    calls the OpenAI transcription API instead. language is an optional
    ISO-639-1 hint (e.g. "en", "es"); if None it is auto-detected.
    """
    audio_path = Path(audio_path)
    if engine == "whisper":
        m = whisper.load_model(model)
        result = m.transcribe(str(audio_path), language=language)
        return result["text"].strip()
    elif engine == "openai":
        client = _require_openai()
        with open(audio_path, "rb") as f:
            result = client.audio.transcriptions.create(
                model="gpt-4o-transcribe", file=f, language=language,
            )
        return result.text.strip()
    raise ValueError(f"Unknown engine: {engine}")


def _extract_frames(video_path: Path, out_dir: Path, count: int = 6) -> list[Path]:
    """Sample roughly `count` evenly-spaced JPEG frames from video_path into
    out_dir via ffmpeg/ffprobe, and return their sorted paths."""
    _require_ffmpeg()
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        check=True, capture_output=True, text=True,
    )
    duration = float(probe.stdout.strip() or 1)
    fps = count / max(duration, 1)
    pattern = str(out_dir / "frame_%02d.jpg")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path), "-vf", f"fps={fps}", pattern],
        check=True, capture_output=True,
    )
    return sorted(out_dir.glob("frame_*.jpg"))


def interpret_video(video_path: Path, prompt: str | None = None) -> str:
    """Produce one combined summary of a video's spoken transcript (via
    OpenAI transcription) and its visual content (via sampled frames sent to
    gpt-4o). Requires OPENAI_API_KEY. prompt overrides the default
    instruction sent to the model."""
    import base64
    video_path = Path(video_path)
    client = _require_openai()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        audio_path = extract_audio_from_video(video_path, tmp / "audio.wav")
        transcript = transcribe_audio(audio_path, engine="openai")
        frames = _extract_frames(video_path, tmp)

        content = [{"type": "text", "text":
            (prompt or "Describe what happens visually in this video, "
                       "then combine it with the spoken transcript below into one coherent summary.")
            + f"\n\nTranscript:\n{transcript}"}]
        for frame in frames:
            b64 = base64.b64encode(frame.read_bytes()).decode()
            content.append({"type": "image_url",
                             "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": content}],
        )
        return response.choices[0].message.content.strip()


def main():
    parser = argparse.ArgumentParser(description="Transcribe audio/video to text")
    parser.add_argument("input", help="Audio file, video file, or Instagram reel URL")
    parser.add_argument("--url", action="store_true", help="Treat input as an Instagram reel URL")
    parser.add_argument("--from-video", action="store_true", help="Extract audio from video input, then transcribe")
    parser.add_argument("--interpret-video", action="store_true", help="Whole-video LLM interpretation (transcript + visual description)")
    parser.add_argument("--engine", default="whisper", choices=["whisper", "openai"], help="Transcription engine (default: whisper)")
    parser.add_argument("-m", "--model", default="base",
                         choices=["tiny", "base", "small", "medium", "large"],
                         help="Whisper model size (default: base)")
    parser.add_argument("-l", "--language", default=None, help="Language hint, e.g. 'en', 'es'")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Output .txt path")
    args = parser.parse_args()

    try:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(args.input)
            if args.url:
                source = download_instagram_reel(args.input, Path(tmp))

            if not args.url and not source.exists():
                print(f"File not found: {source}", file=sys.stderr)
                sys.exit(1)

            if args.interpret_video:
                text = interpret_video(source)
            elif args.from_video:
                audio_path = extract_audio_from_video(source, Path(tmp) / "audio.wav")
                text = transcribe_audio(audio_path, args.engine, args.model, args.language)
            else:
                text = transcribe_audio(source, args.engine, args.model, args.language)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        args.output.write_text(text, encoding="utf-8")
        print(f"Saved to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
