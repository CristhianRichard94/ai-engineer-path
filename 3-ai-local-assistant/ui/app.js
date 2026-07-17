// app.js — JARVIS control UI client.
// Consumes the /state SSE stream from server.py, toggles body.state-* classes,
// renders status text, and wires the two-step Restart button.

(function () {
  "use strict";

  const STATES = [
    "off", "wake_listening", "listening", "thinking",
    "speaking", "error", "restarting",
  ];

  const STATUS_TEXT = {
    off: "JARVIS is offline.",
    wake_listening: "Listening for wake word.",
    listening: "Listening…",
    thinking: "Thinking…",
    speaking: "Speaking…",
    error: null,       // uses detail
    restarting: "Restarting…",
  };

  const body = document.body;
  const statusEl = document.getElementById("status-text");
  const banner = document.getElementById("connection-banner");

  const transcriptLog = document.getElementById("transcript-log");

  const restartBtn = document.getElementById("restart-btn");

  let currentState = "off";
  let thinkingSinceTs = null;
  let thinkingTimer = null;

  let confirmRevertTimer = null;
  let confirmTickTimer = null;
  let confirmSecondsLeft = 0;
  let restartTimeoutTimer = null;
  let optimisticRestarting = false;
  let restartUiState = "idle"; // "idle" | "confirm" | "restarting"

  // ── Status text rendering ──────────────────────────────────────────

  function setBodyState(state) {
    STATES.forEach((s) => body.classList.remove("state-" + s));
    body.classList.add("state-" + state);
  }

  function renderStatus(state, detail) {
    statusEl.classList.toggle("error", state === "error");
    statusEl.setAttribute("aria-live", state === "error" ? "assertive" : "polite");

    if (state === "thinking") {
      statusEl.textContent = "";
      const base = document.createTextNode(STATUS_TEXT.thinking);
      statusEl.appendChild(base);
      if (thinkingSinceTs && Date.now() - thinkingSinceTs > 5000) {
        const span = document.createElement("span");
        span.className = "taking-longer";
        span.textContent = " (taking longer than usual)";
        statusEl.appendChild(span);
      }
      return;
    }

    if (state === "error") {
      statusEl.textContent = detail ? String(detail).slice(0, 200) : "An error occurred, sir.";
      return;
    }

    statusEl.textContent = STATUS_TEXT[state] || "";
  }

  function handleThinkingTimer(state) {
    if (state === "thinking") {
      if (!thinkingSinceTs) {
        thinkingSinceTs = Date.now();
        if (thinkingTimer) clearTimeout(thinkingTimer);
        thinkingTimer = setTimeout(() => {
          if (currentState === "thinking") renderStatus("thinking");
        }, 5000);
      }
    } else {
      thinkingSinceTs = null;
      if (thinkingTimer) {
        clearTimeout(thinkingTimer);
        thinkingTimer = null;
      }
    }
  }

  function applyState(state, detail) {
    currentState = state;
    setBodyState(state);
    handleThinkingTimer(state);
    renderStatus(state, detail);

    // Restart flow: success/failure resolution.
    if (optimisticRestarting) {
      if (state === "wake_listening") {
        optimisticRestarting = false;
        clearRestartTimeout();
        resetRestartButton();
      } else if (state === "error") {
        optimisticRestarting = false;
        clearRestartTimeout();
        resetRestartButton();
      }
    }
  }

  // ── Transcript panel ──────────────────────────────────────────────

  const TRANSCRIPT_POLL_INTERVAL = 1500;
  let transcriptSeenCount = 0;

  function roleLabel(role) {
    return role === "user" ? "You:" : "JARVIS:";
  }

  function renderTranscriptEntries(entries) {
    entries.forEach((entry) => {
      const line = document.createElement("div");
      const roleClass = entry.role === "user" ? "transcript-user" : "transcript-assistant";
      line.className = "transcript-entry " + roleClass;

      const roleSpan = document.createElement("span");
      roleSpan.className = "transcript-role";
      roleSpan.textContent = roleLabel(entry.role);
      line.appendChild(roleSpan);

      line.appendChild(document.createTextNode(String(entry.text || "")));
      transcriptLog.appendChild(line);
    });

    if (entries.length > 0) {
      transcriptLog.scrollTop = transcriptLog.scrollHeight;
    }
  }

  function pollTranscript() {
    fetch("/transcript")
      .then((res) => res.json())
      .then((entries) => {
        if (!Array.isArray(entries)) return;
        if (entries.length < transcriptSeenCount) {
          // Transcript file was reset/rotated - re-render from scratch.
          transcriptLog.textContent = "";
          transcriptSeenCount = 0;
        }
        const newEntries = entries.slice(transcriptSeenCount);
        renderTranscriptEntries(newEntries);
        transcriptSeenCount = entries.length;
      })
      .catch(() => {
        // Ignore transient network errors; next poll will retry.
      });
  }

  pollTranscript();
  setInterval(pollTranscript, TRANSCRIPT_POLL_INTERVAL);

  // ── Connection banner ────────────────────────────────────────────

  let bannerVisible = false;

  function showBanner() {
    if (bannerVisible) return;
    bannerVisible = true;
    banner.hidden = false;
    banner.classList.add("entering");
    requestAnimationFrame(() => banner.classList.remove("entering"));
  }

  function hideBanner() {
    if (!bannerVisible) return;
    bannerVisible = false;
    banner.classList.add("exiting");
    setTimeout(() => {
      banner.hidden = true;
      banner.classList.remove("exiting");
    }, 200);
  }

  // ── SSE connection ───────────────────────────────────────────────

  let es = null;
  let reconnectTimer = null;

  function connect() {
    if (es) {
      es.close();
    }
    es = new EventSource("/state");

    es.onmessage = (evt) => {
      hideBanner();
      try {
        const data = JSON.parse(evt.data);
        applyState(data.state || "off", data.detail || "");
      } catch (e) {
        // ignore malformed payloads
      }
    };

    es.onerror = () => {
      showBanner();
      es.close();
      if (reconnectTimer) clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(connect, 1500);
    };
  }

  connect();

  // ── Restart button (single element, state-cycling + optimistic UI) ──

  const CONFIRM_WINDOW_SECONDS = 4;

  function clearConfirmTimers() {
    if (confirmRevertTimer) {
      clearTimeout(confirmRevertTimer);
      confirmRevertTimer = null;
    }
    if (confirmTickTimer) {
      clearInterval(confirmTickTimer);
      confirmTickTimer = null;
    }
  }

  function clearRestartTimeout() {
    if (restartTimeoutTimer) {
      clearTimeout(restartTimeoutTimer);
      restartTimeoutTimer = null;
    }
  }

  function resetRestartButton() {
    restartUiState = "idle";
    clearConfirmTimers();
    restartBtn.className = "restart-btn state-idle";
    restartBtn.disabled = false;
    restartBtn.removeAttribute("aria-label");
    restartBtn.innerHTML = '<span class="restart-btn-label">Restart JARVIS</span>';
  }

  function updateConfirmLabel() {
    const text = "Confirm restart? (" + confirmSecondsLeft + ")";
    restartBtn.innerHTML = '<span class="restart-btn-label">' + text + "</span>";
    restartBtn.setAttribute(
      "aria-label",
      "Confirm restart, " + confirmSecondsLeft + " seconds remaining"
    );
  }

  function revertToIdle() {
    resetRestartButton();
    // Only touch the shared status line if we were the ones driving it
    // (i.e. don't clobber a state pushed by SSE in the meantime).
    if (currentState !== "restarting" && currentState !== "error") {
      renderStatus(currentState, "");
    }
  }

  function enterConfirmMode() {
    restartUiState = "confirm";
    clearConfirmTimers();
    restartBtn.className = "restart-btn state-confirm";
    confirmSecondsLeft = CONFIRM_WINDOW_SECONDS;
    updateConfirmLabel();

    statusEl.setAttribute("aria-live", "polite");
    statusEl.classList.remove("error");
    statusEl.textContent =
      "Restart requires confirmation. Click again within 4 seconds, or press Escape to cancel.";

    confirmTickTimer = setInterval(() => {
      confirmSecondsLeft -= 1;
      if (confirmSecondsLeft <= 0) {
        clearConfirmTimers();
        revertToIdle();
        return;
      }
      updateConfirmLabel();
    }, 1000);

    confirmRevertTimer = setTimeout(() => {
      clearConfirmTimers();
      revertToIdle();
    }, CONFIRM_WINDOW_SECONDS * 1000);
  }

  function commitRestart() {
    clearConfirmTimers();
    restartUiState = "restarting";
    restartBtn.className = "restart-btn state-restarting";
    restartBtn.disabled = true;
    restartBtn.removeAttribute("aria-label");
    restartBtn.innerHTML =
      '<span class="restart-spinner" aria-hidden="true"></span><span class="restart-btn-label">Restarting…</span>';

    optimisticRestarting = true;
    applyState("restarting", "");

    fetch("/restart", { method: "POST" }).catch(() => {
      // Network failure calling restart: let the 15s timeout handle it.
    });

    clearRestartTimeout();
    restartTimeoutTimer = setTimeout(() => {
      if (optimisticRestarting) {
        optimisticRestarting = false;
        applyState("error", "Restart failed — JARVIS did not come back online.");
        resetRestartButton();
      }
    }, 15000);
  }

  restartBtn.addEventListener("click", () => {
    if (restartUiState === "idle") {
      enterConfirmMode();
    } else if (restartUiState === "confirm") {
      commitRestart();
    }
    // No-op while "restarting" — button is disabled anyway.
  });

  restartBtn.addEventListener("keydown", (evt) => {
    if (evt.key === "Escape" && restartUiState === "confirm") {
      evt.preventDefault();
      clearConfirmTimers();
      revertToIdle();
    }
  });
})();
