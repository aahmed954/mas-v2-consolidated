#!/bin/bash
# Simple ingestion script - assumes services are already running
set -euo pipefail

# Paths
LIFE_DIR="/home/starlord/raycastfiles/Life"
METRO_DIR="/home/starlord/mas-v2-crewai/cases_to_process/Metro"
ROOT_DIR="/home/starlord/mas-v2-crewai/cases_to_process"

cd ~/mas-v2-consolidated
source .venv/bin/activate
[ -f .env ] && source .env

COLLECTION="${COLLECTION:-mas_ingest_d768}"
UVICORN_PORT="${UVICORN_PORT:-8002}"
QDRANT_URL="${QDRANT_URL:-http://127.0.0.1:6333}"
API="http://127.0.0.1:${UVICORN_PORT}"

# Helper function
count() { 
  curl -s -X POST "${QDRANT_URL}/collections/${COLLECTION}/points/count" \
    -H 'Content-Type: application/json' -d '{"exact":true}' | jq -r '.result.count // 0'
}

echo "[I] Starting ingestion to collection: ${COLLECTION}"
echo "[I] Initial point count: $(count)"

# 1. Life directory
if [ -d "${LIFE_DIR}" ]; then
  echo "[I] Enqueue 1/3: LIFE -> ${LIFE_DIR}"
  curl -s -X POST "${API}/ingest_folder" -H "Content-Type: application/json" \
    -d "{\"remote_folder_path\":\"${LIFE_DIR}\",\"collection\":\"${COLLECTION}\"}" | jq .
  echo "[I] Monitoring for 1 minute..."
  for i in {1..6}; do 
    sleep 10
    echo "  points=$(count) @ $(date +%H:%M:%S)"
  done
fi

# 2. Metro directory
if [ -d "${METRO_DIR}" ]; then
  echo "[I] Enqueue 2/3: METRO -> ${METRO_DIR}"
  curl -s -X POST "${API}/ingest_folder" -H "Content-Type: application/json" \
    -d "{\"remote_folder_path\":\"${METRO_DIR}\",\"collection\":\"${COLLECTION}\"}" | jq .
  echo "[I] Monitoring for 1 minute..."
  for i in {1..6}; do 
    sleep 10
    echo "  points=$(count) @ $(date +%H:%M:%S)"
  done
fi

# 3. Remaining directories
if [ -d "${ROOT_DIR}" ]; then
  echo "[I] Discovering remaining folders..."
  mapfile -t REST < <(find "${ROOT_DIR}" -maxdepth 1 -mindepth 1 -type d ! -name "Metro" | sort)
  echo "[I] Found ${#REST[@]} additional folders"
  
  for d in "${REST[@]}"; do
    echo "  -> Enqueuing: $d"
    curl -s -X POST "${API}/ingest_folder" -H "Content-Type: application/json" \
      -d "{\"remote_folder_path\":\"${d}\",\"collection\":\"${COLLECTION}\"}" | jq -c '.status // .ok // .'
    sleep 2
  done
fi

echo "[✓] All folders queued. Final monitoring..."
for i in {1..12}; do 
  echo "  points=$(count) @ $(date +%H:%M:%S)"
  sleep 10
done

echo "[✓] Ingestion complete. Total points: $(count)"