"""
spotify_player.py - Spotify integration for JARVIS.

Two modes:
  - Client Credentials (default): search only. Playback via URI launch (no Premium needed).
  - OAuth (SPOTIFY_USE_OAUTH=true): full playback API control (Premium required).

Setup: create an app at https://developer.spotify.com/dashboard
then add SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to .env
"""

import os
import subprocess

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth


class SpotifyAuthError(Exception):
    """Raised when Spotify credentials are missing or rejected."""


class SpotifyPlayer:
    SCOPES = "user-read-playback-state user-modify-playback-state"

    def __init__(self, client_id, client_secret,
                 redirect_uri="http://localhost:8888/callback", use_oauth=False):
        self.use_oauth = use_oauth

        if use_oauth:
            auth = SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                scope=self.SCOPES,
                open_browser=True,
                cache_path=os.path.join(os.path.dirname(__file__), ".spotify_cache"),
            )
        else:
            auth = SpotifyClientCredentials(
                client_id=client_id,
                client_secret=client_secret,
            )

        self.sp = spotipy.Spotify(auth_manager=auth)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search_and_play(self, query):
        """Search for a track and play it. Returns a spoken reply."""
        track = self._search_track(query)
        if track is None:
            return "No track found for '{}', sir.".format(query)

        name     = track["name"]
        artist   = track["artists"][0]["name"]
        track_id = track["id"]
        uri      = track["uri"]

        if self.use_oauth:
            played = self._play_via_api(uri)
            if played:
                return "Playing '{}' by {}, sir.".format(name, artist)

        self._play_via_uri(track_id)
        return "Opening '{}' by {} in Spotify, sir.".format(name, artist)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _search_track(self, query):
        """Return the first track result dict, or None. Raises SpotifyAuthError on bad creds."""
        try:
            results = self.sp.search(q=query, type="track", limit=1)
            items = results.get("tracks", {}).get("items", [])
            return items[0] if items else None
        except spotipy.exceptions.SpotifyException as e:
            if "invalid_client" in str(e) or e.http_status in (400, 401):
                raise SpotifyAuthError(
                    "Spotify credentials are invalid or missing. "
                    "Please add SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to your .env file. "
                    "Get them at https://developer.spotify.com/dashboard"
                ) from e
            print("[SPOTIFY] Search error: {}".format(e))
            return None
        except Exception as e:
            print("[SPOTIFY] Search error: {}".format(e))
            return None

    def _play_via_api(self, uri):
        """Use Spotify Web API to start playback. Returns True on success."""
        try:
            self.sp.start_playback(uris=[uri])
            return True
        except Exception as e:
            print("[SPOTIFY] Playback API error (Premium required?): {}".format(e))
            return False

    def _play_via_uri(self, track_id):
        """Open Spotify desktop app to the track via URI scheme."""
        uri = "spotify:track:{}".format(track_id)
        try:
            # os.startfile is the correct Windows API for registered URI handlers
            os.startfile(uri)
        except AttributeError:
            # Non-Windows fallback
            subprocess.Popen(["cmd", "/c", "start", "", uri], shell=True)
        except Exception as e:
            print("[SPOTIFY] URI launch error: {}".format(e))
