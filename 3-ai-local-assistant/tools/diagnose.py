"""
diagnose.py - JARVIS configuration checker.

Run this from your venv to verify everything is set up correctly:
  venv\Scripts\python.exe diagnose.py
"""

import os
import sys

# Load .env so we see the same values JARVIS sees
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("[!] python-dotenv not installed — .env will NOT be loaded")

print("=" * 60)
print("JARVIS DIAGNOSTICS")
print("=" * 60)

# ------------------------------------------------------------------
# 1. Python version
# ------------------------------------------------------------------
print("\n[1] Python version: {}".format(sys.version))

# ------------------------------------------------------------------
# 2. ElevenLabs / TTS
# ------------------------------------------------------------------
print("\n[2] TTS (ElevenLabs)")
el_key   = os.getenv("ELEVENLABS_API_KEY", "")
el_voice = os.getenv("ELEVENLABS_VOICE_ID", "")
if not el_key:
    print("    ELEVENLABS_API_KEY : NOT SET  ← TTS will use pyttsx3 fallback")
else:
    print("    ELEVENLABS_API_KEY : SET ({})".format(el_key[:8] + "..."))
if not el_voice:
    print("    ELEVENLABS_VOICE_ID: NOT SET")
else:
    print("    ELEVENLABS_VOICE_ID: {}".format(el_voice))

# Quick API test
if el_key and el_voice:
    try:
        from elevenlabs.client import ElevenLabs
        client = ElevenLabs(api_key=el_key)
        # Just call voices list as a connectivity check
        voices = client.voices.get_all()
        names = [v.name for v in (voices.voices or [])[:3]]
        print("    API connectivity  : OK — voices: {}".format(names))
    except Exception as e:
        print("    API connectivity  : FAILED — {}".format(e))

# ------------------------------------------------------------------
# 3. Spotify
# ------------------------------------------------------------------
print("\n[3] Spotify")
sp_id     = os.getenv("SPOTIFY_CLIENT_ID", "")
sp_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "")
sp_oauth  = os.getenv("SPOTIFY_USE_OAUTH", "false")

placeholder = lambda v: v.startswith("your_") or not v

if placeholder(sp_id):
    print("    SPOTIFY_CLIENT_ID    : PLACEHOLDER — create an app at")
    print("                           https://developer.spotify.com/dashboard")
else:
    print("    SPOTIFY_CLIENT_ID    : SET ({})".format(sp_id[:6] + "..."))

if placeholder(sp_secret):
    print("    SPOTIFY_CLIENT_SECRET: PLACEHOLDER")
else:
    print("    SPOTIFY_CLIENT_SECRET: SET")

print("    SPOTIFY_USE_OAUTH    : {}".format(sp_oauth))

if not placeholder(sp_id) and not placeholder(sp_secret):
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
            client_id=sp_id, client_secret=sp_secret
        ))
        results = sp.search(q="test", type="track", limit=1)
        print("    API test             : OK")
    except Exception as e:
        print("    API test             : FAILED — {}".format(e))

# ------------------------------------------------------------------
# 4. Audio output switching / nircmd
# ------------------------------------------------------------------
print("\n[4] Audio switching")
nircmd_path = os.getenv("NIRCMD_PATH") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "switch-audio-output", "nircmd.exe"
)
if os.path.exists(nircmd_path):
    print("    nircmd.exe found : {}".format(nircmd_path))
else:
    print("    nircmd.exe MISSING at {}".format(nircmd_path))
    print("    Download from https://www.nirsoft.net/utils/nircmd.html")
    print("    and place in the switch-audio-output/ folder.")

spk = os.getenv("AUDIO_DEVICE_SPEAKER", "")
hdp = os.getenv("AUDIO_DEVICE_HEADPHONES", "")
print("    AUDIO_DEVICE_SPEAKER    : '{}'".format(spk))
print("    AUDIO_DEVICE_HEADPHONES : '{}'".format(hdp))

# List actual Windows playback devices using pycaw
print("\n    Actual Windows playback devices (from pycaw):")
try:
    from pycaw.pycaw import AudioUtilities
    devices = AudioUtilities.GetAllDevices()
    playback = [d for d in devices if "render" in str(d.flow).lower() or d.flow == 0]
    if not playback:
        # Try all devices if flow filtering gives nothing
        playback = devices
    for d in playback:
        match_spk = "(matches SPEAKER env)" if d.FriendlyName == spk else ""
        match_hdp = "(matches HEADPHONES env)" if d.FriendlyName == hdp else ""
        print("      - \"{}\" {} {}".format(d.FriendlyName, match_spk, match_hdp))
    print()
    print("    Copy one of the names above into your .env:")
    print("      AUDIO_DEVICE_SPEAKER=<exact name>")
    print("      AUDIO_DEVICE_HEADPHONES=<exact name>")
except Exception as e:
    print("    Could not list devices: {}".format(e))

# ------------------------------------------------------------------
# 5. Microphone / input devices
# ------------------------------------------------------------------
print("\n[5] Microphone (input devices)")
try:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "jarvis"))
    import sounddevice as sd
    from audio_input import find_input_device, _is_virtual, NoMicrophoneError

    print("    All input-capable devices (from sounddevice):")
    try:
        devices = sd.query_devices()
        input_devices = [
            (i, d) for i, d in enumerate(devices) if d.get('max_input_channels', 0) > 0
        ]
        if not input_devices:
            print("      (none found)")
        for i, d in input_devices:
            flag = " [virtual/loopback]" if _is_virtual(d.get('name', '')) else ""
            print("      - index {}: \"{}\" (max_input_channels={}){}".format(
                i, d.get('name', '?'), d.get('max_input_channels', 0), flag))
    except Exception as e:
        print("    Could not list input devices: {}".format(e))

    print("\n    Resolved microphone (what JARVIS will actually use):")
    try:
        index, rate = find_input_device()
        info = sd.query_devices(index)
        resolved_is_virtual = _is_virtual(info.get('name', ''))
        print("      -> index {}: \"{}\" ({} Hz)".format(index, info.get('name', '?'), rate))
        if resolved_is_virtual:
            print("      WARNING: resolved device name matches the virtual/loopback filter -")
            print("               this shouldn't normally happen; the filter should have")
            print("               skipped it in favor of a real microphone.")
        else:
            print("      OK: resolved device is not flagged as virtual/loopback.")
    except NoMicrophoneError as e:
        print("    FAILED: {}".format(e))
except ImportError as e:
    print("    Could not check microphone: {}".format(e))

# ------------------------------------------------------------------
# 6. OpenAI
# ------------------------------------------------------------------
print("\n[6] OpenAI")
oai_key = os.getenv("OPENAI_API_KEY", "")
if not oai_key:
    print("    OPENAI_API_KEY: NOT SET")
else:
    print("    OPENAI_API_KEY: SET ({})".format(oai_key[:8] + "..."))

# ------------------------------------------------------------------
# 7. Wake word models
# ------------------------------------------------------------------
print("\n[7] Wake word models")
try:
    import openwakeword
    models_dir = os.path.join(
        os.path.dirname(os.path.abspath(openwakeword.__file__)),
        "resources", "models"
    )
    for fname in ["hey_jarvis_v0.1.onnx", "melspectrogram.onnx", "embedding_model.onnx"]:
        path = os.path.join(models_dir, fname)
        status = "OK" if os.path.exists(path) else "MISSING"
        print("    {} : {}".format(fname, status))
except ImportError:
    print("    openwakeword not installed")

print("\n" + "=" * 60)
print("Done. Fix any FAILED / PLACEHOLDER items above, then run JARVIS.")
print("=" * 60)
