"""
audio_switcher.py — Windows audio output device switcher for JARVIS.

Wraps nircmd.exe (https://www.nirsoft.net/utils/nircmd.html) to change
the default playback device by name.

Device names MUST match exactly what Windows shows in:
  Control Panel → Sound → Playback (tab)

Configure your device names in .env:
  AUDIO_DEVICE_SPEAKER=Altavoces (Realtek(R) Audio)
  AUDIO_DEVICE_HEADPHONES=Realtek HD Audio 2nd output (Realtek(R) Audio)
"""

import os
import subprocess


class AudioSwitcher:
    # Friendly aliases the user / GPT can say → map to .env keys
    _ALIAS_MAP: dict[str, str] = {
        "speaker":    "AUDIO_DEVICE_SPEAKER",
        "speakers":   "AUDIO_DEVICE_SPEAKER",
        "headphones": "AUDIO_DEVICE_HEADPHONES",
        "headphone":  "AUDIO_DEVICE_HEADPHONES",
        "earphones":  "AUDIO_DEVICE_HEADPHONES",
    }

    def __init__(self, nircmd_path: str | None = None):
        # Resolve nircmd path: explicit arg → env var → same dir as this file
        if nircmd_path:
            self.nircmd = nircmd_path
        elif os.getenv("NIRCMD_PATH"):
            self.nircmd = os.getenv("NIRCMD_PATH")
        else:
            self.nircmd = os.path.join(
                os.path.dirname(__file__),
                "switch-audio-output",
                "nircmd.exe",
            )

        # Device name registry (resolved at init so tests can override env)
        self._devices: dict[str, str] = {
            alias: os.getenv(env_key, "")
            for alias, env_key in self._ALIAS_MAP.items()
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def switch(self, device_name: str) -> str:
        """Switch the default audio output to the named device.

        Args:
            device_name: friendly name, e.g. 'headphones' or 'speaker'.

        Returns:
            A spoken reply string for JARVIS to say.
        """
        key    = device_name.lower().strip()
        device = self._devices.get(key)

        if not device:
            known = ", ".join(sorted({v for v in self._ALIAS_MAP.keys()}))
            return (
                f"I don't recognise '{device_name}' as an audio device, sir. "
                f"Try one of: {known}."
            )

        return self._run_nircmd(device, device_name)

    def list_aliases(self) -> list[str]:
        """Return the supported friendly alias names."""
        return sorted(self._ALIAS_MAP.keys())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_nircmd(self, windows_device_name: str, friendly_name: str) -> str:
        try:
            subprocess.run(
                [self.nircmd, "setdefaultsounddevice", windows_device_name],
                check=True,
                capture_output=True,
            )
            return f"Audio output switched to {friendly_name}, sir."
        except FileNotFoundError:
            return (
                "Audio switcher unavailable, sir. "
                "nircmd.exe was not found."
            )
        except subprocess.CalledProcessError as e:
            print(f"[AUDIO] nircmd error: {e.stderr}")
            return "Failed to switch audio output, sir."
        except Exception as e:
            print(f"[AUDIO] Unexpected error: {e}")
            return "An unexpected error occurred while switching audio, sir."
