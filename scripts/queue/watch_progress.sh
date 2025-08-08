#!/usr/bin/env bash
set -euo pipefail

while true; do
  clear
  echo "=== MAS v2 Forensic Queue Status ==="
  echo "Time: $(date)"
  echo
  
  # Queue counts
  running=$(find ~/.queue_state/running -type f 2>/dev/null | wc -l)
  done=$(find ~/.queue_state/done -type f 2>/dev/null | wc -l)
  failed=$(find ~/.queue_state/failed -type f 2>/dev/null | wc -l)
  
  echo "Queue Summary:"
  echo "  Running: $running"
  echo "  Done:    $done"
  echo "  Failed:  $failed"
  echo
  
  # Current jobs
  echo "Active Jobs:"
  for f in ~/.queue_state/running/*; do
    [[ -f "$f" ]] && echo "  - $(basename "$f")"
  done 2>/dev/null || echo "  (none)"
  echo
  
  # Resource usage
  cpu=$(./scripts/queue/monitor_resources.sh | grep "CPU Usage:" | awk '{print $3}')
  gpu=$(./scripts/queue/monitor_resources.sh | grep "GPU Usage:" | awk '{print $3}')
  mem=$(./scripts/queue/monitor_resources.sh | grep "Memory:" | awk '{print $2, $3, $4, $5, $6}')
  disk=$(./scripts/queue/monitor_resources.sh | grep "Free disk:" | awk '{print $3, $4, $5}')
  
  echo "Resources:"
  echo "  CPU:  $cpu"
  echo "  GPU:  $gpu"
  echo "  Mem:  $mem"
  echo "  Disk: $disk"
  echo
  
  # Latest log snippet
  echo "Latest Activity:"
  latest_log=$(ls -t ~/mas-v2-consolidated/logs/queue/*.log 2>/dev/null | head -1)
  if [[ -n "$latest_log" ]]; then
    echo "  From: $(basename "$latest_log")"
    tail -5 "$latest_log" | sed 's/^/  /'
  else
    echo "  No logs yet"
  fi
  
  sleep 5
done