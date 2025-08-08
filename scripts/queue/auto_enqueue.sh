#!/usr/bin/env bash
set -euo pipefail

# === Config ===
BASE_DIR="${1:-/home/starlord/mas-v2-crewai/cases_to_process}"
MAX_PARALLEL="${MAX_PARALLEL:-3}"            # hard cap
CPU_HIGH_WATER="${CPU_HIGH_WATER:-90}"       # % overall
GPU_HIGH_WATER="${GPU_HIGH_WATER:-90}"       # % util on GPU0
MIN_FREE_GB="${MIN_FREE_GB:-40}"             # don't start if less free on /home
SCOPE_SLICE="masv2-queue.slice"

REPO="$HOME/mas-v2-consolidated"
STATE="$REPO/.queue_state"
RUNNING_DIR="$STATE/running"
DONE_DIR="$STATE/done"
FAILED_DIR="$STATE/failed"
LOG_DIR="$REPO/logs/queue"
mkdir -p "$RUNNING_DIR" "$DONE_DIR" "$FAILED_DIR" "$LOG_DIR"

QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
export QDRANT_URL

# === Helpers ===

cpu_usage() {
  # % busy computed from /proc/stat (aggregate) over 1s interval
  # Ref math: /proc/stat idle vs total delta.
  read -r cpu a b c d rest < /proc/stat
  idle1=$d; total1=$((a+b+c+d))
  sleep 1
  read -r cpu a b c d rest < /proc/stat
  idle2=$d; total2=$((a+b+c+d))
  idle=$((idle2-idle1)); total=$((total2-total1))
  busy=$((100*(total-idle)/ (total==0?1:total) ))
  echo "$busy"
}

gpu_usage() {
  # needs nvidia-smi; prints util.gpu % of GPU0 or 0 if missing
  if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits | head -n1 2>/dev/null | tr -d ' ' || echo 0
  else
    echo 0
  fi
}

free_gb() {
  df -BG /home | awk 'NR==2{gsub("G","",$4); print $4}'
}

jobs_running() {
  find "$RUNNING_DIR" -type f | wc -l | tr -d ' '
}

launch_job() {
  folder="$1"
  name="$(basename "$folder")"
  stamp="$(date +%Y%m%d-%H%M%S)"
  log="$LOG_DIR/${stamp}-${name}.log"

  touch "$RUNNING_DIR/$name"

  # Run in a systemd scope with CPU/mem caps; polite IO; mild nice
  # systemd resource controls: CPUQuota/MemoryMax.
  systemd-run --user --scope --slice="$SCOPE_SLICE" \
    -p CPUQuota=90% -p MemoryMax=58G \
    bash -lc "cd '$REPO' && source ~/.venvs/masv2/bin/activate && \
      ionice -c2 -n2 nice -n5 scripts/forensics/run_forensic_ingest.sh '$folder' >> '$log' 2>&1" \
    >/dev/null

  echo "LAUNCHED: $name (log: $log)"
}

mark_done() {
  name="$1"
  mv -f "$RUNNING_DIR/$name" "$DONE_DIR/$name" 2>/dev/null || true
}

mark_failed() {
  name="$1"
  mv -f "$RUNNING_DIR/$name" "$FAILED_DIR/$name" 2>/dev/null || true
}

# === Build queue (Metro first if present) ===
mapfile -t items < <(find "$BASE_DIR" -mindepth 1 -maxdepth 1 -type d -printf "%f\n" | sort)
queue=()
for d in "${items[@]}"; do
  [[ "$d" == "Metro" ]] && queue+=("$BASE_DIR/$d")
done
for d in "${items[@]}"; do
  [[ "$d" == "Metro" ]] && continue
  queue+=("$BASE_DIR/$d")
done

# Filter out already-done
filtered=()
for f in "${queue[@]}"; do
  name="$(basename "$f")"
  [[ -f "$DONE_DIR/$name" ]] && continue
  filtered+=("$f")
done
queue=("${filtered[@]}")

echo "Queue length: ${#queue[@]} (base: $BASE_DIR)"
echo "Max parallel: $MAX_PARALLEL  CPU cap: ${CPU_HIGH_WATER}%  GPU cap: ${GPU_HIGH_WATER}%  Min free: ${MIN_FREE_GB}GB"

# === Supervisor loop ===
declare -A attempts
while :; do
  # cleanup completed: anything in RUNNING with no systemd process still writing → mark done
  # (crude: if log hasn't grown in 10min and point count for folder known → leave; we keep simple here)

  # start new jobs if capacity & headroom allow
  curr=$(jobs_running)
  if (( curr < MAX_PARALLEL && ${#queue[@]} > 0 )); then
    cpu=$(cpu_usage)
    gpu=$(gpu_usage)
    free=$(free_gb)
    if (( cpu < CPU_HIGH_WATER && gpu < GPU_HIGH_WATER && free > MIN_FREE_GB )); then
      folder="${queue[0]}"; queue=("${queue[@]:1}")
      name="$(basename "$folder")"
      launch_job "$folder" || true
    fi
  fi

  # sweep logs for completion markers
  for r in "$RUNNING_DIR"/*; do
    [[ -f "$r" ]] || continue
    name="$(basename "$r")"
    # consider job finished when its ingest log ends with "ALL CHECKS PASSED" or "pipeline completed" marker
    lastlog="$(ls -t "$LOG_DIR"/*-"$name".log 2>/dev/null | head -n1 || true)"
    if [[ -n "$lastlog" ]]; then
      if tail -n1 "$lastlog" | grep -qiE 'completed|ALL CHECKS PASSED'; then
        mark_done "$name"
        echo "DONE: $name"
      fi
      if grep -qiE 'Traceback|ERROR|failed' "$lastlog"; then
        # retry up to 2x
        attempts["$name"]=$(( ${attempts["$name"]:-0} + 1 ))
        if (( attempts["$name"] <= 2 )); then
          echo "RETRY: $name (attempt ${attempts["$name"]})"
          launch_job "$BASE_DIR/$name"
        else
          mark_failed "$name"
          echo "FAILED: $name (see $lastlog)"
        fi
      fi
    fi
  done

  # exit when nothing is queued or running
  if (( ${#queue[@]} == 0 )) && (( $(jobs_running) == 0 )); then
    echo "Queue empty and no jobs running. Exiting."
    exit 0
  fi
  sleep 15
done