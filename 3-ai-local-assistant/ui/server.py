"""
ui/server.py - Local control UI for JARVIS.

Flask app that:
  - Serves the built React control UI from ui/frontend/dist/
    (run `npm install && npm run build` inside ui/frontend/ first)
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
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request, send_from_directory

_UI_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_UI_DIR, os.pardir))
_MAIN_PY = os.path.join(_REPO_ROOT, "main.py")
_DIST_DIR = os.path.join(_UI_DIR, "frontend", "dist")

load_dotenv()

sys.path.append(os.path.join(_REPO_ROOT, "jarvis"))
from state import STATE_FILE, TRANSCRIPT_FILE, write_state, request_history_reset, append_transcript  # noqa: E402
from brain import JarvisBrain  # noqa: E402
from router import IntentRouter  # noqa: E402
from vault import write_session_note  # noqa: E402

app = Flask(__name__, static_folder=None)

_CHAT_MESSAGE_MAX_CHARS = 4000

# Lazily-created shared JarvisBrain/IntentRouter for the text-chat endpoint.
# Both are stateful (brain.history, router's pending-slot state) and are
# only ever touched under _chat_lock, since Flask runs threaded=True and
# multiple /chat requests could otherwise interleave.
_chat_lock = threading.Lock()
_brain = None
_router = None


def _get_chat_components():
    """Lazily instantiate the shared JarvisBrain/IntentRouter used by /chat.

    Must only be called while holding _chat_lock.
    """
    global _brain, _router
    if _brain is None:
        _brain = JarvisBrain(api_key=os.getenv("OPENAI_API_KEY"))
    if _router is None:
        _router = IntentRouter()
    return _brain, _router


def _resume_conversation(brain, conversation_id):
    """Reconstruct brain.history from transcript.jsonl lines tagged with
    `conversation_id`, capped to brain.max_history turns, and point
    brain.conversation_id at it so subsequent appends land in the same
    conversation.

    Note: transcript.jsonl only ever stores plain spoken text, so this
    loses the classifier's raw-JSON-assistant-turn shape - resumed history
    reads as plain chat turns even for past action-intent turns. Accepted
    simplification, must only be called while holding _chat_lock.
    """
    entries = _read_transcript(limit=None, conversation_id=conversation_id)
    history = [
        {"role": e["role"], "content": e["text"]}
        for e in entries if e.get("role") in ("user", "assistant")
    ][-brain.max_history:]
    brain.history = history
    brain.conversation_id = conversation_id

PORT = int(os.getenv("JARVIS_UI_PORT", "5151"))

_STALE_SECONDS = 10
_POLL_INTERVAL = 0.15  # ~6-7x/sec
_RESTART_TERMINATE_TIMEOUT = 5
_TRANSCRIPT_MAX_ENTRIES = 50


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


def _read_transcript(limit=_TRANSCRIPT_MAX_ENTRIES, conversation_id=None):
    """Return transcript entries, oldest first.

    `limit` caps the number of entries returned (the most recent `limit`);
    pass `limit=None` for no cap (returns everything). When
    `conversation_id` is given, entries are filtered to that conversation
    *before* the limit is applied, so a long-running conversation isn't
    starved by unrelated lines from other conversations. When
    `conversation_id` is None, all entries are considered (today's
    behavior for the unscoped case).

    Tolerates a missing file (no conversation yet) and skips any malformed
    lines rather than failing the whole request.
    """
    if not os.path.exists(TRANSCRIPT_FILE):
        return []

    entries = []
    try:
        with open(TRANSCRIPT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if conversation_id is not None and entry.get("conversation_id") != conversation_id:
                    continue
                entries.append(entry)
    except OSError:
        return []

    if limit is None:
        return entries
    return entries[-limit:]


# ── Routes ─────────────────────────────────────────────────────────────
#
# The control UI is a React app (ui/frontend/), built with `npm run build`
# into ui/frontend/dist/. This server just serves that static bundle.

@app.route("/")
def index():
    if not os.path.exists(os.path.join(_DIST_DIR, "index.html")):
        return (
            "Frontend build not found. Run `npm install && npm run build` "
            "inside ui/frontend/ first.",
            500,
        )
    return send_from_directory(_DIST_DIR, "index.html")


@app.route("/assets/<path:filename>")
def assets(filename):
    return send_from_directory(os.path.join(_DIST_DIR, "assets"), filename)


@app.route("/state")
def state_stream():
    def generate():
        last_payload = None
        while True:
            current = _read_state()
            payload_dict = {
                "state": current.get("state", "off"),
                "detail": current.get("detail", ""),
                "ts": current.get("ts", time.time()),
            }
            # Only present while state == "speaking" (see write_state()) -
            # pass it through unchanged so the frontend can drive the orb.
            if "amplitude" in current:
                payload_dict["amplitude"] = current["amplitude"]
            # Sourced from the lazily-created /chat brain only - the voice
            # loop (main.py) runs in a separate process with its own
            # JarvisBrain instance we have no access to here, so this is
            # None/absent until at least one /chat message has been sent
            # in this server process (known, accepted limitation).
            if _brain is not None:
                payload_dict["conversation_id"] = _brain.conversation_id
            payload = json.dumps(payload_dict)
            if payload != last_payload:
                last_payload = payload
                yield "data: {}\n\n".format(payload)
            time.sleep(_POLL_INTERVAL)

    return Response(generate(), mimetype="text/event-stream")


@app.route("/transcript")
def transcript():
    conversation_id = request.args.get("conversation_id")
    if not conversation_id and _brain is not None:
        conversation_id = _brain.conversation_id
    return jsonify(_read_transcript(conversation_id=conversation_id))


@app.route("/conversations")
def conversations():
    """List past conversations derived from transcript.jsonl by grouping
    entries by conversation_id, in chronological order of first
    appearance. Untagged (legacy or voice-loop) lines have no
    conversation_id and are skipped rather than forming a bogus group."""
    entries = _read_transcript(limit=None, conversation_id=None)
    groups = {}
    order = []
    for e in entries:
        if not isinstance(e, dict) or "ts" not in e or "role" not in e:
            continue
        cid = e.get("conversation_id")
        if cid is None:
            continue
        if cid not in groups:
            groups[cid] = {
                "conversation_id": cid,
                "first_ts": e["ts"],
                "last_ts": e["ts"],
                "turn_count": 0,
                "preview": None,
            }
            order.append(cid)
        g = groups[cid]
        g["last_ts"] = e["ts"]
        g["turn_count"] += 1
        if g["preview"] is None and e.get("role") == "user":
            g["preview"] = e.get("text", "")[:80]
    return jsonify([groups[cid] for cid in order])


@app.route("/chat", methods=["POST"])
def chat():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "invalid request body"}), 400

    message = body.get("message")
    if not isinstance(message, str) or not message.strip():
        return jsonify({"error": "message must be a non-empty string"}), 400
    if len(message) > _CHAT_MESSAGE_MAX_CHARS:
        return jsonify({"error": "message is too long"}), 400

    resume_id = body.get("conversation_id")
    if resume_id is not None and not isinstance(resume_id, str):
        return jsonify({"error": "conversation_id must be a string"}), 400

    try:
        with _chat_lock:
            brain, router = _get_chat_components()
            if resume_id and resume_id != brain.conversation_id:
                _resume_conversation(brain, resume_id)
            parsed = brain.think(message)
            reply = router.dispatch(parsed, raw_text=message)

            intent = parsed.get("intent", "chat") if isinstance(parsed, dict) else "chat"

            # Transcript writes for this turn happen inside the same lock as
            # think()/dispatch() so that two concurrent /chat requests can
            # never interleave their user/assistant lines out of order.
            # Best-effort: a write failure here must not turn a successful
            # dispatch (which may already have caused a real side effect,
            # e.g. opening an app) into an HTTP 500 - just log it.
            try:
                append_transcript("user", message, conversation_id=brain.conversation_id)
                append_transcript("assistant", reply, conversation_id=brain.conversation_id)
            except Exception as e:
                print("[CHAT] Failed to append transcript: {}".format(e))
    except Exception as e:
        # Don't leak stack traces / local paths into the HTTP response body.
        print("[CHAT] Failed to process message: {}".format(e))
        return jsonify({"error": "failed to process message"}), 500

    try:
        write_session_note(intent, message, reply)
    except Exception as e:
        print("[CHAT] Failed to write session note: {}".format(e))

    return jsonify({"reply": reply, "intent": intent})


@app.route("/restart", methods=["POST"])
def restart():
    threading.Thread(target=_do_restart, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/new-conversation", methods=["POST"])
def new_conversation():
    with _chat_lock:
        if _brain is not None:
            _brain.reset_history()

    jarvis_running = _jarvis_is_running()
    if jarvis_running:
        # Only meaningful if a live process will actually consume it - a
        # freshly started process already begins with empty brain.history,
        # so writing a signal for it to find later would just be stale.
        request_history_reset()

    return jsonify({"ok": True, "jarvis_running": jarvis_running})


def _find_jarvis_process():
    """Return the live psutil.Process running main.py, or None if not found."""
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            if any("main.py" in str(part) for part in cmdline):
                return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def _jarvis_is_running():
    """True if a live process whose cmdline references main.py is found."""
    return _find_jarvis_process() is not None


def _do_restart():
    write_state("restarting")

    target = _find_jarvis_process()

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
