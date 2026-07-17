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

  const idleBtn = document.getElementById("restart-idle-btn");
  const confirmWrapper = document.getElementById("restart-confirm-wrapper");
  const confirmBtn = document.getElementById("restart-confirm-btn");
  const cancelBtn = document.getElementById("restart-cancel-btn");

  let currentState = "off";
  let thinkingSinceTs = null;
  let thinkingTimer = null;

  let confirmRevertTimer = null;
  let restartTimeoutTimer = null;
  let optimisticRestarting = false;

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

  // ── Restart button (two-step + optimistic UI) ────────────────────

  function resetRestartButton() {
    idleBtn.hidden = false;
    idleBtn.disabled = false;
    idleBtn.innerHTML = "Restart JARVIS";
    confirmWrapper.hidden = true;
  }

  function showConfirmMode() {
    idleBtn.hidden = true;
    confirmWrapper.hidden = false;
    if (confirmRevertTimer) clearTimeout(confirmRevertTimer);
    confirmRevertTimer = setTimeout(() => {
      confirmWrapper.hidden = true;
      idleBtn.hidden = false;
    }, 4000);
  }

  function clearRestartTimeout() {
    if (restartTimeoutTimer) {
      clearTimeout(restartTimeoutTimer);
      restartTimeoutTimer = null;
    }
  }

  function commitRestart() {
    if (confirmRevertTimer) {
      clearTimeout(confirmRevertTimer);
      confirmRevertTimer = null;
    }
    confirmWrapper.hidden = true;
    idleBtn.hidden = false;
    idleBtn.disabled = true;
    idleBtn.innerHTML = '<span class="restart-spinner" aria-hidden="true"></span> Restarting…';

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

  idleBtn.addEventListener("click", showConfirmMode);

  confirmBtn.addEventListener("click", commitRestart);
  confirmBtn.addEventListener("keydown", (evt) => {
    if (evt.key === "Enter" || evt.key === " ") {
      evt.preventDefault();
      commitRestart();
    }
  });

  cancelBtn.addEventListener("click", () => {
    if (confirmRevertTimer) {
      clearTimeout(confirmRevertTimer);
      confirmRevertTimer = null;
    }
    confirmWrapper.hidden = true;
    idleBtn.hidden = false;
  });
})();
