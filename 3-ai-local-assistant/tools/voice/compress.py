from pydub import AudioSegment

# Load your uncompressed WAV file
audio = AudioSegment.from_wav("input.wav")

# Export as MP3 with a controlled bitrate (e.g., 128k or 192k)
audio.export("compressed.mp3", format="mp3", bitrate="128k")
