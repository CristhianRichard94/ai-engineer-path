"""
state.py - Writes JARVIS's current lifecycle state to state.json for the
control UI (ui/server.py) to poll and stream via SSE.

State file lives at the repo root (one level above jarvis/) so both the
jarvis process and the ui server agree on a single, well-known path.

Write is atomic (write to a .tmp file, then os.replace()) so the UI server
never reads a half-written file.
"""

import json
import os
import time

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
STATE_FILE = os.path.join(_REPO_ROOT, "state.json")


def write_state(state: str, detail: str = ""):
    """Atomically write the current state to state.json.

    state: one of off | wake_listening | listening | thinking | speaking |
           error | restarting
    detail: optional extra text (e.g. transcribed command, error message)
    """
    payload = {
        "state": state,
        "detail": detail,
        "ts": time.time(),
        "pid": os.getpid(),
    }

    tmp_path = STATE_FILE + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp_path, STATE_FILE)
    except OSError as e:
        # Best-effort: state reporting should never crash JARVIS itself.
        print("[STATE] Failed to write state.json: {}".format(e))
