"""
test/spotify_player.py — Unit tests for SpotifyPlayer.

No real Spotify API calls are made; spotipy is fully mocked.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch, call

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Stub spotipy before importing the module under test
for mod in ("spotipy", "spotipy.oauth2", "spotipy.exceptions"):
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

import spotify_player as sp_module
from spotify_player import SpotifyPlayer


def _make_player(use_oauth=False) -> SpotifyPlayer:
    with patch("spotify_player.SpotifyClientCredentials"), \
         patch("spotify_player.SpotifyOAuth"), \
         patch("spotify_player.spotipy.Spotify") as mock_sp_cls:
        player = SpotifyPlayer(
            client_id="test-id",
            client_secret="test-secret",
            use_oauth=use_oauth,
        )
        player.sp = mock_sp_cls.return_value
    return player


def _fake_track(name="Africa", artist="Toto", track_id="track123"):
    return {
        "name"   : name,
        "id"     : track_id,
        "uri"    : f"spotify:track:{track_id}",
        "artists": [{"name": artist}],
    }


# ════════════════════════════════════════════════════════════════════════
# _search_track
# ════════════════════════════════════════════════════════════════════════

class TestSearchTrack(unittest.TestCase):

    def setUp(self):
        self.player = _make_player()

    def test_returns_first_track_on_success(self):
        track = _fake_track()
        self.player.sp.search.return_value = {
            "tracks": {"items": [track]}
        }
        result = self.player._search_track("Africa Toto")
        self.assertEqual(result, track)

    def test_returns_none_when_no_items(self):
        self.player.sp.search.return_value = {"tracks": {"items": []}}
        result = self.player._search_track("xyzzy_nonexistent")
        self.assertIsNone(result)

    def test_returns_none_on_api_exception(self):
        self.player.sp.search.side_effect = Exception("API down")
        result = self.player._search_track("anything")
        self.assertIsNone(result)

    def test_passes_query_to_spotify_search(self):
        self.player.sp.search.return_value = {"tracks": {"items": []}}
        self.player._search_track("Bohemian Rhapsody Queen")
        self.player.sp.search.assert_called_once_with(
            q="Bohemian Rhapsody Queen", type="track", limit=1
        )


# ════════════════════════════════════════════════════════════════════════
# _play_via_uri
# ════════════════════════════════════════════════════════════════════════

class TestPlayViaUri(unittest.TestCase):

    def setUp(self):
        self.player = _make_player()

    @patch("spotify_player.subprocess.Popen")
    def test_opens_correct_spotify_uri(self, mock_popen):
        self.player._play_via_uri("track123")
        mock_popen.assert_called_once_with(
            ["cmd", "/c", "start", "", "spotify:track:track123"],
            shell=False,
        )

    @patch("spotify_player.subprocess.Popen", side_effect=Exception("popen fail"))
    def test_does_not_raise_on_popen_error(self, _):
        # Should swallow the exception gracefully
        try:
            self.player._play_via_uri("track123")
        except Exception:
            self.fail("_play_via_uri raised unexpectedly")


# ════════════════════════════════════════════════════════════════════════
# _play_via_api
# ════════════════════════════════════════════════════════════════════════

class TestPlayViaApi(unittest.TestCase):

    def setUp(self):
        self.player = _make_player(use_oauth=True)

    def test_returns_true_on_success(self):
        self.player.sp.start_playback.return_value = None
        result = self.player._play_via_api("spotify:track:abc")
        self.assertTrue(result)
        self.player.sp.start_playback.assert_called_once_with(
            uris=["spotify:track:abc"]
        )

    def test_returns_false_on_spotify_exception(self):
        import spotipy.exceptions as exc_mod
        exc_mod.SpotifyException = Exception  # already mocked; just use Exception
        self.player.sp.start_playback.side_effect = Exception("Premium required")
        result = self.player._play_via_api("spotify:track:abc")
        self.assertFalse(result)

    def test_returns_false_on_generic_exception(self):
        self.player.sp.start_playback.side_effect = RuntimeError("oops")
        result = self.player._play_via_api("spotify:track:abc")
        self.assertFalse(result)


# ════════════════════════════════════════════════════════════════════════
# search_and_play (integration of search + playback)
# ════════════════════════════════════════════════════════════════════════

class TestSearchAndPlay(unittest.TestCase):

    def setUp(self):
        self.player = _make_player(use_oauth=False)

    def _stub_search(self, track):
        self.player.sp.search.return_value = {
            "tracks": {"items": [track] if track else []}
        }

    @patch("spotify_player.subprocess.Popen")
    def test_returns_opening_reply_on_success(self, mock_popen):
        self._stub_search(_fake_track("Africa", "Toto", "t1"))
        reply = self.player.search_and_play("Africa Toto")
        self.assertIn("Africa", reply)
        self.assertIn("Toto", reply)
        mock_popen.assert_called_once()

    def test_returns_not_found_reply_when_no_results(self):
        self._stub_search(None)
        reply = self.player.search_and_play("xyzzy_garbage_123")
        self.assertIn("No track found", reply)
        self.assertIn("xyzzy_garbage_123", reply)

    @patch("spotify_player.subprocess.Popen")
    def test_uses_uri_launch_when_not_oauth(self, mock_popen):
        track = _fake_track("Song", "Artist", "tid99")
        self._stub_search(track)
        self.player.search_and_play("Song Artist")
        # Should call Popen (URI launch), NOT sp.start_playback
        mock_popen.assert_called_once()
        self.player.sp.start_playback.assert_not_called()

    @patch("spotify_player.subprocess.Popen")
    def test_oauth_mode_uses_api_then_falls_back_to_uri_if_api_fails(self, mock_popen):
        self.player.use_oauth = True
        track = _fake_track("Song", "Artist", "tid42")
        self._stub_search(track)
        self.player.sp.start_playback.side_effect = Exception("Premium required")
        reply = self.player.search_and_play("Song")
        # Should still fall through to URI launch
        mock_popen.assert_called_once()
        self.assertIn("Song", reply)

    @patch("spotify_player.subprocess.Popen")
    def test_oauth_mode_uses_api_and_skips_uri_when_api_succeeds(self, mock_popen):
        self.player.use_oauth = True
        track = _fake_track("Song", "Artist", "tid42")
        self._stub_search(track)
        self.player.sp.start_playback.return_value = None
        reply = self.player.search_and_play("Song")
        mock_popen.assert_not_called()
        self.assertIn("Playing", reply)
        self.assertIn("Song", reply)


if __name__ == "__main__":
    unittest.main()
