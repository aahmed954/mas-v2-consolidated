#!/usr/bin/env bash
set -euo pipefail

# --- config ---
PORTS=(6333 6334 9090 9091 3000 6379 6380 16686 14268)
SERVICES=(qdrant redis-server redis prometheus grafana)
OUR_CONTAINERS_REGEX='masv2-|qdrant/qdrant'
AUTO_FIX="${AUTO_FIX:-1}"      # 1=try to fix; 0=read-only audit
FORCE_KILL_SECS="${FORCE_KILL_SECS:-7}"

echo "== Ports/Services Guard =="

echo "-- Docker containers bound to our ports --"
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}' | egrep -i "${OUR_CONTAINERS_REGEX}" || true
echo

echo "-- Systemd services of interest --"
systemctl list-units --type=service | egrep -i 'qdrant|redis|prometheus|grafana' || true
echo

echo "-- LISTEN PIDs on important ports --"
for p in "${PORTS[@]}"; do
  (sudo lsof -i :"$p" -sTCP:LISTEN -P -n || true) | awk -v port="$p" 'NR==1{print} NR>1{print} END{if(NR==0) print "no listeners on :" port}'
done
echo

if [ "$AUTO_FIX" != "1" ]; then
  echo "[INFO] AUTO_FIX=0 (audit-only). Set AUTO_FIX=1 to stop/kill stale holders."
  exit 0
fi

echo "== Attempting to free our expected ports =="

# allow-list: do NOT stop our running Qdrant
ALLOW_IMAGES_REGEX="^(qdrant/qdrant)(:.*)?$"
ALLOW_NAMES_REGEX="^(masv2-qdrant)$"

# 1) Stop our known containers that expose these ports EXCEPT allow-listed ones
if docker ps --format '{{.Names}} {{.Ports}}' | egrep -i "${OUR_CONTAINERS_REGEX}" >/dev/null 2>&1; then
  echo "[INFO] Processing docker containers matching ${OUR_CONTAINERS_REGEX}..."
  for id in $(docker ps --format '{{.ID}} {{.Names}} {{.Image}}' | egrep -i "${OUR_CONTAINERS_REGEX}" | awk '{print $1}'); do
    img="$(docker inspect --format='{{.Config.Image}}' "$id" 2>/dev/null || echo '')"
    name="$(docker inspect --format='{{.Name}}' "$id" 2>/dev/null | sed 's#^/##' || echo '')"
    if [[ "$img" =~ $ALLOW_IMAGES_REGEX ]] || [[ "$name" =~ $ALLOW_NAMES_REGEX ]]; then
      echo "[INFO] Skipping allow-listed container: $name ($img)"
      continue
    fi
    echo "[INFO] Stopping container: $name ($img)"
    docker stop "$id"
  done
fi

# 2) Stop system services that might still be pinned
for svc in "${SERVICES[@]}"; do
  if systemctl is-active --quiet "$svc"; then
    echo "[INFO] Stopping systemd service: $svc"
    sudo systemctl stop "$svc" || true
  fi
done

# 3) Kill any remaining listeners on the ports
for p in "${PORTS[@]}"; do
  PIDS=$(sudo lsof -t -i :"$p" -sTCP:LISTEN || true)
  if [ -n "$PIDS" ]; then
    echo "[WARN] Processes still listening on :$p -> $PIDS"
    echo "      Sending SIGTERM..."
    sudo kill $PIDS || true
    for i in $(seq "$FORCE_KILL_SECS" -1 1); do
      sleep 1
      REM=$(sudo lsof -t -i :"$p" -sTCP:LISTEN || true)
      [ -z "$REM" ] && break
    done
    REM=$(sudo lsof -t -i :"$p" -sTCP:LISTEN || true)
    if [ -n "$REM" ]; then
      echo "[WARN] Force killing stubborn listeners on :$p -> $REM"
      sudo kill -9 $REM || true
    fi
  fi
done

echo
echo "== Post-clean audit =="
for p in "${PORTS[@]}"; do
  (sudo lsof -i :"$p" -sTCP:LISTEN -P -n || true) | awk -v port="$p" 'NR==1{print} NR>1{print} END{if(NR==0) print "no listeners on :" port}'
done
echo "Guard complete."