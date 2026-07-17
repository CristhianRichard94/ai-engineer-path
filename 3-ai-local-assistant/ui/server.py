"""
ui/server.py - Local control UI for JARVIS.

Flask app that:
  - Serves the static control UI (index.html, app.js, animation.css)
  - Streams JARVIS's current lifecycle state via SSE (GET /state)
  - Restarts the JARVIS process on request (POST /restart)

Run with:  python ui/server.py
This opens the default browser at http://127.0.0.1:<port>/ automatically.
"""

import json
import os
import subprocess
import sys
import threading
import time
import webbrowser

import psutil
from flask import Flask, Response, jsonify, send_from_directory

_UI_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_UI_DIR, os.pardir))
_MAIN_PY = os.path.join(_REPO_ROOT, "main.py")

sys.path.append(os.path.join(_REPO_ROOT, "jarvis"))
from state import STATE_FILE, write_state  # noqa: E402

app = Flask(__name__, static_folder=None)

PORT = int(os.getenv("JARVIS_UI_PORT", "5151"))

_STALE_SECONDS = 10
_POLL_INTERVAL = 0.15  # ~6-7x/sec
_RESTART_TERMINATE_TIMEOUT = 5


# ── State reading ─────────────────────────────────────────────────────

def _pid_is_jarvis(pid):
    """True if `pid` is a live process whose cmdline references main.py."""
    try:
        proc = psutil.Process(pid)
        cmdline = " ".join(proc.cmdline()).lower()
        return "main.py" in cmdline
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False


def _read_state():
    """Return the current state dict, falling back to 'off' when the state
    file is missing, unreadable, or stale with no matching live process."""
    if not os.path.exists(STATE_FILE):
        return {"state": "off", "detail": "", "ts": time.time(), "pid": None}

    try:
        mtime = os.stat(STATE_FILE).st_mtime
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, ValueError):
        return {"state": "off", "detail": "", "ts": time.time(), "pid": None}

    age = time.time() - mtime
    pid = data.get("pid")

    if age > _STALE_SECONDS and not _pid_is_jarvis(pid):
        return {"state": "off", "detail": "", "ts": time.time(), "pid": pid}

    return data


# ── Routes ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(_UI_DIR, "index.html")


@app.route("/app.js")
def app_js():
    return send_from_directory(_UI_DIR, "app.js")


@app.route("/animation.css")
def animation_css():
    return send_from_directory(_UI_DIR, "animation.css")


@app.route("/state")
def state_stream():
    def generate():
        last_payload = None
        while True:
            current = _read_state()
            payload = json.dumps({
                "state": current.get("state", "off"),
                "detail": current.get("detail", ""),
                "ts": current.get("ts", time.time()),
            })
            if payload != last_payload:
                last_payload = payload
                yield "data: {}\n\n".format(payload)
            time.sleep(_POLL_INTERVAL)

    return Response(generate(), mimetype="text/event-stream")


@app.route("/restart", methods=["POST"])
def restart():
    threading.Thread(target=_do_restart, daemon=True).start()
    return jsonify({"ok": True})


def _do_restart():
    write_state("restarting")

    target = None
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            if any("main.py" in str(part) for part in cmdline):
                target = proc
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if target is not None:
        try:
            target.terminate()
            target.wait(timeout=_RESTART_TERMINATE_TIMEOUT)
        except psutil.TimeoutExpired:
            try:
                target.kill()
            except psutil.NoSuchProcess:
                pass
        except psutil.NoSuchProcess:
            pass

    subprocess.Popen(
        [sys.executable, _MAIN_PY],
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        cwd=_REPO_ROOT,
    )


def main():
    url = "http://127.0.0.1:{}/".format(PORT)
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=PORT, threaded=True)


if __name__ == "__main__":
    main()
