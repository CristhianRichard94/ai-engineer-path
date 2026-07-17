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
TRANSCRIPT_FILE = os.path.join(_REPO_ROOT, "transcript.jsonl")
CLAUDE_AUDIT_FILE = os.path.join(_REPO_ROOT, "claude_cli_audit.jsonl")


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


def append_transcript(role: str, text: str):
    """Append a single conversation turn to transcript.jsonl.

    role: "user" | "assistant"
    text: the transcribed/spoken text for this turn

    This is a simple append-only log (not atomic like write_state) - safe
    because each write is a single line and we never rewrite prior lines.
    """
    if not text:
        return

    line = json.dumps({
        "role": role,
        "text": text,
        "ts": time.time(),
    })

    try:
        with open(TRANSCRIPT_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as e:
        # Best-effort: transcript logging should never crash JARVIS itself.
        print("[STATE] Failed to append transcript.jsonl: {}".format(e))


def append_claude_audit(prompt: str, stdout: str, stderr: str, returncode):
    """Append a full, untruncated record of a Claude Code CLI invocation
    to claude_cli_audit.jsonl.

    This is separate from the (possibly truncated) spoken reply, so the
    full prompt sent to the agentic CLI and everything it printed can be
    reviewed after the fact.

    prompt    : the full prompt string passed to `claude -p`
    stdout    : full, untruncated stdout captured from the process
    stderr    : full, untruncated stderr captured from the process
    returncode: process return code, or None if the process never
                completed (e.g. timeout / exception before completion)
    """
    line = json.dumps({
        "ts": time.time(),
        "prompt": prompt,
        "result": {"stdout": stdout, "stderr": stderr},
        "returncode": returncode,
    })

    try:
        with open(CLAUDE_AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as e:
        # Best-effort: audit logging should never crash JARVIS itself.
        print("[STATE] Failed to append claude_cli_audit.jsonl: {}".format(e))
