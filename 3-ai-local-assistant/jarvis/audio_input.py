# audio_input.py — shared microphone-resolution logic for wake_word.py and stt.py
import sounddevice as sd

# Case-insensitive name substrings that flag a device as virtual/loopback
# rather than a real physical microphone.
_VIRTUAL_DEVICE_MARKERS = ("stereo mix", "cable", "loopback", "virtual")


class NoMicrophoneError(Exception):
    """Raised when no usable input (microphone) device can be found."""
    pass


def _is_virtual(name: str) -> bool:
    name_lower = (name or "").lower()
    return any(marker in name_lower for marker in _VIRTUAL_DEVICE_MARKERS)


def find_input_device():
    """Resolve which input device to capture audio from.

    Resolution order:
      1. Trust the OS/user-configured default input device (sd.default.device[0])
         if it's set and valid.
      2. Otherwise scan all devices for input-capable ones, preferring a real
         (non-virtual/loopback) microphone.
      3. If every input-capable device looks virtual, fall back to the first
         one found anyway rather than failing outright.
      4. Raise NoMicrophoneError only if there is truly no input-capable
         device at all.

    Returns (index, samplerate).
    """
    index = sd.default.device[0]
    info = None
    if index is not None and index >= 0:
        try:
            info = sd.query_devices(index)
        except Exception as e:
            print("[MIC] Default input device (index {}) unavailable: {}".format(index, e))
            info = None
        else:
            if info is not None and _is_virtual(info.get('name', '')):
                print("[MIC] Default input device (index {}: {}) looks virtual/loopback "
                      "- scanning for a real microphone instead.".format(index, info.get('name', '')))
                info = None

    if info is None:
        # No OS default input device (or querying it failed) - fall back
        # to scanning all devices for a usable microphone, preferring a
        # real (non-virtual/loopback) one.
        print("[MIC] No default input device - scanning for a usable microphone...")
        try:
            devices = sd.query_devices()
        except Exception as e:
            raise NoMicrophoneError(
                "No microphone found. Check your audio input device is connected."
            ) from e

        first_fallback = None  # first input-capable device, virtual or not
        for i, dev in enumerate(devices):
            if dev.get('max_input_channels', 0) > 0:
                if first_fallback is None:
                    first_fallback = (i, dev)
                if not _is_virtual(dev.get('name', '')):
                    index, info = i, dev
                    break

        if info is None and first_fallback is not None:
            # Every input-capable device looked virtual (or none were
            # preferred) - fall back to the first one found rather than
            # failing outright.
            index, info = first_fallback

    if info is None:
        raise NoMicrophoneError(
            "No microphone found. Check your audio input device is connected."
        )

    print("[MIC] Using -> index {}: {} ({} Hz)".format(
        index, info['name'], info['default_samplerate']))
    return index, info['default_samplerate']
