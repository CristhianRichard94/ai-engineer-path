"""
router.py - Intent dispatcher for JARVIS.

Maps intent names (from brain.py) to concrete Windows/API actions.
"""

import os
import subprocess
import webbrowser
from datetime import datetime

import psutil
import requests

from spotify_player import SpotifyPlayer, SpotifyAuthError


class IntentRouter:
    def __init__(self):
        self.weather_key  = os.getenv("OPENWEATHER_API_KEY")
        self.default_city = os.getenv("DEFAULT_CITY", "Buenos Aires")

        # Spotify player (lazy-loaded on first use)
        self._spotify = None

        # Route table: intent name -> method name on this class.
        # Using method NAMES (not bound methods) so that tests can replace
        # instance methods via attribute assignment and dispatch sees the patch.
        self._routes = {
            "open_app"       : "open_app",
            "close_app"      : "close_app",
            "search_web"     : "search_web",
            "get_time"       : "get_time",
            "get_weather"    : "get_weather",
            "get_system_info": "get_system_info",
            "set_volume"     : "set_volume",
            "open_folder"    : "open_folder",
            "play_spotify"   : "play_spotify",
            "goodbye"        : "goodbye",
            "chat"           : "do_nothing",
        }

        # Intents whose handler returns the spoken reply (data-driven)
        self._DATA_INTENTS = {
            "get_weather",
            "get_system_info",
            "get_time",
            "play_spotify",
        }

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def dispatch(self, parsed):
        intent = parsed.get("intent", "chat")
        params = parsed.get("params", {})
        reply  = parsed.get("reply", "Done, sir.")

        method_name = self._routes.get(intent, "do_nothing")
        fn = getattr(self, method_name, self.do_nothing)

        if intent in self._DATA_INTENTS:
            result = fn(params)
            return result if result else reply
        else:
            fn(params)
            return reply

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def open_app(self, p):
        apps = {
            "notepad"   : "notepad.exe",
            "chrome"    : r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "explorer"  : "explorer.exe",
            "calculator": "calc.exe",
            "spotify"   : r"C:\Users\%USERNAME%\AppData\Roaming\Spotify\Spotify.exe",
        }
        exe = apps.get(p["app"].lower(), p["app"])
        subprocess.Popen(exe, shell=True)

    def close_app(self, p):
        name = p["app"].lower().replace(".exe", "")
        for proc in psutil.process_iter(["name"]):
            if name in proc.info["name"].lower():
                proc.kill()

    def search_web(self, p):
        webbrowser.open("https://google.com/search?q={}".format(p["query"]))

    def get_time(self, p):
        now = datetime.now()
        return "It is {}, sir.".format(now.strftime("%I:%M %p"))

    def get_system_info(self, p):
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory()
        return (
            "CPU at {}%, RAM {}% used "
            "({:.1f} GB of {:.1f} GB), sir.".format(
                cpu,
                ram.percent,
                ram.used / (1024 ** 3),
                ram.total / (1024 ** 3),
            )
        )

    def set_volume(self, p):
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        devices = AudioUtilities.GetSpeakers()
        iface   = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume  = cast(iface, POINTER(IAudioEndpointVolume))
        level   = max(0, min(100, int(p["level"]))) / 100
        volume.SetMasterVolumeLevelScalar(level, None)

    def open_folder(self, p):
        subprocess.Popen('explorer "{}"'.format(p["path"]))

    def play_spotify(self, p):
        query = p.get("query", "").strip()
        if not query:
            return "Please tell me what to play, sir."

        player = self._get_spotify()
        if player is None:
            return ("Spotify is not configured, sir. "
                    "Please add your SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to the .env file.")

        try:
            return player.search_and_play(query)
        except SpotifyAuthError as e:
            print("[SPOTIFY] Auth error: {}".format(e))
            return ("Spotify credentials are invalid, sir. "
                    "Please check your SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in the .env file.")
        except Exception as e:
            print("[SPOTIFY] Unexpected error: {}".format(e))
            return "There was an error connecting to Spotify, sir."

    def goodbye(self, p):
        # Signals main.py to end the current session; reply comes from GPT
        pass

    def do_nothing(self, p):
        pass

    def get_weather(self, p):
        city = p.get("city", "current")
        if city in ("current", "", None):
            city = self.default_city

        try:
            resp = requests.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={
                    "q"    : city,
                    "appid": self.weather_key,
                    "units": "metric",
                    "lang" : "en",
                },
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()

            temp      = round(data["main"]["temp"])
            feels     = round(data["main"]["feels_like"])
            desc      = data["weather"][0]["description"]
            humidity  = data["main"]["humidity"]
            city_name = data["name"]

            return (
                "{}: {}, {}C, feels like {}C, humidity {}%.".format(
                    city_name, desc, temp, feels, humidity
                )
            )

        except requests.exceptions.Timeout:
            return "Weather service timed out, sir."
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return "I couldn't find weather data for {}, sir.".format(city)
            return "Weather service returned an error, sir."
        except Exception as e:
            print("[WEATHER] Error: {}".format(e))
            return "I was unable to fetch the weather, sir."

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_spotify(self):
        """Lazily initialise SpotifyPlayer when credentials are present."""
        if self._spotify is not None:
            return self._spotify

        client_id     = os.getenv("SPOTIFY_CLIENT_ID", "")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "")
        redirect_uri  = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")
        use_oauth     = os.getenv("SPOTIFY_USE_OAUTH", "false").lower() == "true"

        if not client_id or not client_secret:
            return None

        try:
            self._spotify = SpotifyPlayer(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                use_oauth=use_oauth,
            )
        except Exception as e:
            print("[SPOTIFY] Init error: {}".format(e))
            return None

        return self._spotify
