#!/bin/bash
# jarvis-entrypoint.sh
# Runs inside the Fish Speech container.
# 1. Downloads model checkpoints from HuggingFace on first run.
# 2. Starts the API server on port 8080.

set -euo pipefail

CHECKPOINT_DIR="${CHECKPOINT_DIR:-/app/checkpoints/fish-speech-1.5}"
HF_REPO="${HF_REPO:-fishaudio/fish-speech-1.5}"
LISTEN="${LISTEN:-0.0.0.0:8080}"

log() { echo "[$(date '+%H:%M:%S')] [JARVIS-TTS] $*"; }

# ── 1. Download checkpoints ────────────────────────────────────────────────
if [ ! -f "${CHECKPOINT_DIR}/codec.pth" ]; then
    log "Checkpoints not found. Downloading ${HF_REPO} ..."
    log "This may take several minutes on first run (~3 GB)."

    uv run python - <<PYEOF
import os
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id="${HF_REPO}",
    local_dir="${CHECKPOINT_DIR}",
    ignore_patterns=["*.ot", "*.onnx", "*.safetensors.index.json"],
)
print("Checkpoints ready at ${CHECKPOINT_DIR}")
PYEOF
    log "Download complete."
else
    log "Checkpoints already present at ${CHECKPOINT_DIR}"
fi

# ── 2. Verify reference voice exists ──────────────────────────────────────
JARVIS_REF="/app/references/jarvis"
if [ ! -d "${JARVIS_REF}" ]; then
    log "WARNING: ${JARVIS_REF} not found. Voice cloning will use default voice."
    log "Mount your references/ directory to enable JARVIS voice cloning."
else
    AUDIO_COUNT=$(find "${JARVIS_REF}" -name "*.mp3" -o -name "*.wav" -o -name "*.flac" 2>/dev/null | wc -l)
    log "JARVIS reference voice ready (${AUDIO_COUNT} audio file(s))."
fi

# ── 3. Start the API server ────────────────────────────────────────────────
log "Starting Fish Speech API server at ${LISTEN} ..."
log "Using checkpoints: ${CHECKPOINT_DIR}"

exec uv run tools/api_server.py \
    --listen "${LISTEN}" \
    --llama-checkpoint-path "${CHECKPOINT_DIR}" \
    --decoder-checkpoint-path "${CHECKPOINT_DIR}/codec.pth" \
    --decoder-config-name "modded_dac_vq" \
    --device cpu
