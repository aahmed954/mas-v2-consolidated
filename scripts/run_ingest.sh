#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

LOG_DIR="${LOG_DIR:-logs}"
mkdir -p "$LOG_DIR"

# ensure venv
if [ -z "${VIRTUAL_ENV-}" ]; then
  if [ -d "$HOME/.venvs/masv2" ]; then
    source "$HOME/.venvs/masv2/bin/activate"
  fi
fi

TS=$(date +%Y%m%d-%H%M%S)
LOG="$LOG_DIR/ingest-$TS.log"

echo "[run_ingest] starting at $TS" | tee -a "$LOG"
echo "[run_ingest] Together model: ${TOGETHER_EMBEDDING_MODEL:-unset}" | tee -a "$LOG"

# health check first (skip m2-bert)
SKIP_M2BERT=1 PYTHONPATH=. python scripts/embed_healthcheck.py | tee -a "$LOG"

# start your normal entrypoint (adjust if needed)
# using nohup so systemd isn't required; logs captured
nohup bash -lc './final_launch.sh' >> "$LOG" 2>&1 &
echo $! > "$LOG_DIR/ingest.pid"
echo "[run_ingest] spawned PID $(cat "$LOG_DIR/ingest.pid") logging to $LOG"