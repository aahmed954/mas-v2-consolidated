#!/usr/bin/env bash
set -euo pipefail

STATE="$HOME/mas-v2-consolidated/.queue_state"
LOG="$HOME/mas-v2-consolidated/logs/provider_watcher.log"
SLACK="${SLACK_WEBHOOK:-}"

mkdir -p "$STATE" "$(dirname "$LOG")"
LAST=""

notify(){
  [ -z "$SLACK" ] && return
  curl -s -X POST -H 'Content-type: application/json' \
    --data "{\"text\":\":arrows_counterclockwise: Embedding provider switched to *$1*\"}" \
    "$SLACK" >/dev/null || true
}

while :; do
  cur="$(tail -n 500 "$HOME/mas-v2-consolidated/logs/embedding.log" 2>/dev/null | \
        grep -Eo 'provider=(together|local)' | tail -n1 | sed 's/provider=//')"
  [ -z "$cur" ] && { sleep 10; continue; }
  if [ "$cur" != "$LAST" ]; then
    echo "$(date -Is) provider=$cur" | tee -a "$LOG"
    notify "$cur"
    LAST="$cur"
  fi
  sleep 10
done


