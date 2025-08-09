#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="${1:-/home/starlord/mas-v2-crewai/cases_to_process}"
MAX_PARALLEL="${MAX_PARALLEL:-8}"
CPU_HIGH_WATER="${CPU_HIGH_WATER:-99}"
GPU_HIGH_WATER="${GPU_HIGH_WATER:-98}"
MIN_FREE_GB="${MIN_FREE_GB:-20}"
SCOPE_SLICE="masv2-queue.slice"
REPO="$HOME/mas-v2-consolidated"
STATE="$REPO/.queue_state"; RUNNING_DIR="$STATE/running"; DONE_DIR="$STATE/done"; FAILED_DIR="$STATE/failed"; LOG_DIR="$REPO/logs/queue"
mkdir -p "$RUNNING_DIR" "$DONE_DIR" "$FAILED_DIR" "$LOG_DIR"

cpu_usage(){ read -r _ a b c d _ < /proc/stat; idle1=$d; t1=$((a+b+c+d)); sleep 1; read -r _ a b c d _ < /proc/stat; idle2=$d; t2=$((a+b+c+d)); echo $((100*( (t2-t1)-(idle2-idle1) )/ ( (t2-t1)==0?1:(t2-t1) ) )); }
gpu_usage(){ command -v nvidia-smi >/dev/null && nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits | head -n1 | tr -d ' ' || echo 0; }
free_gb(){ df -BG /home | awk 'NR==2{gsub("G","",$4);print $4}'; }
jobs_running(){ find "$RUNNING_DIR" -type f | wc -l | tr -d ' '; }
launch_job(){ folder="$1"; name="$(basename "$folder")"; stamp="$(date +%Y%m%d-%H%M%S)"; log="$LOG_DIR/${stamp}-${name}.log"; touch "$RUNNING_DIR/$name";
  systemd-run --user --scope --slice="$SCOPE_SLICE" -p CPUQuota=100% -p MemoryMax=60G \
    bash -lc "cd '$REPO' && source ~/.venvs/masv2/bin/activate && ionice -c2 -n2 nice -n5 scripts/forensics/run_forensic_ingest.sh '$folder' >> '$log' 2>&1" >/dev/null
  echo "LAUNCHED: $name -> $log"; }
mark_done(){ mv -f "$RUNNING_DIR/$1" "$DONE_DIR/$1" 2>/dev/null || true; }
mark_failed(){ mv -f "$RUNNING_DIR/$1" "$FAILED_DIR/$1" 2>/dev/null || true; }

mapfile -t items < <(find "$BASE_DIR" -mindepth 1 -maxdepth 1 -type d -printf "%f\n" | sort); queue=()
for d in "${items[@]}"; do [[ "$d" == "Metro" ]] && queue+=("$BASE_DIR/$d"); done
for d in "${items[@]}"; do [[ "$d" == "Metro" ]] && continue; queue+=("$BASE_DIR/$d"); done
filtered=(); for f in "${queue[@]}"; do name="$(basename "$f")"; [[ -f "$DONE_DIR/$name" ]] && continue; filtered+=("$f"); done; queue=("${filtered[@]}")
echo "Queue: ${#queue[@]} folders"
declare -A attempts
while :; do
  [[ -f "$STATE/desired_parallel" ]] && dp="$(cat "$STATE/desired_parallel" 2>/dev/null || true)" && [[ "$dp" =~ ^[0-9]+$ ]] && MAX_PARALLEL="$dp"
  curr=$(jobs_running)
  if (( curr < MAX_PARALLEL && ${#queue[@]} > 0 )); then
    cpu=$(cpu_usage); gpu=$(gpu_usage); free=$(free_gb)
    if (( cpu < CPU_HIGH_WATER && gpu < GPU_HIGH_WATER && free > MIN_FREE_GB )); then folder="${queue[0]}"; queue=("${queue[@]:1}"); launch_job "$folder"; fi
  fi
  for r in "$RUNNING_DIR"/*; do [[ -f "$r" ]] || continue; name="$(basename "$r")"
    lastlog="$(ls -t "$LOG_DIR"/*-"$name".log 2>/dev/null | head -n1 || true)"
    [[ -n "$lastlog" ]] && { tail -n1 "$lastlog" | grep -qiE 'completed|ALL CHECKS PASSED' && { mark_done "$name"; echo "DONE: $name"; }; \
      grep -qiE 'Traceback|ERROR|failed' "$lastlog" && { attempts["$name"]=$(( ${attempts["$name"]:-0} + 1 )); if (( attempts["$name"] <= 2 )); then echo "RETRY: $name (${attempts["$name"]})"; launch_job "$BASE_DIR/$name"; else mark_failed "$name"; echo "FAILED: $name -> $lastlog"; fi; }; }
  done
  (( ${#queue[@]} == 0 )) && (( $(jobs_running) == 0 )) && { echo "All done."; exit 0; }
  sleep 15
done




