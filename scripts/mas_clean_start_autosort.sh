#!/bin/bash
# ====================== MAS: CLEAN START + SMART AUTO-SORT ======================
set -euo pipefail

# --- 0) ENV / PATHS ---
COLLECTION="${COLLECTION:-mas_ingest_d768}"
EMBED_DIM="${EMBED_DIM:-768}"
QDRANT_URL="${QDRANT_URL:-http://127.0.0.1:6333}"
UVICORN_PORT="${UVICORN_PORT:-8002}"

LIFE_DIR="/home/starlord/raycastfiles/Life"
METRO_DIR="/home/starlord/mas-v2-crewai/cases_to_process/Metro"
ROOT_DIR="/home/starlord/mas-v2-crewai/cases_to_process"

cd ~/mas-v2-consolidated
# venv (prefer project venv, fallback to user venv)
source .venv/bin/activate 2>/dev/null || source ~/.venvs/masv2/bin/activate
export PYTHONPATH=$PWD
# Source .env file if it exists
[ -f .env ] && source .env

# --- 1) Stop app; ensure Redis; reset Qdrant cleanly ---
echo "[I] Stopping user services (API/workers)…"
systemctl --user stop masv2-api masv2-workers 2>/dev/null || true

echo "[I] Ensure Redis on :6379 (host network)…"
docker rm -f masv2-redis-host 2>/dev/null || true
docker run -d --name masv2-redis-host --network host redis:7-alpine \
  redis-server --appendonly yes >/dev/null

echo "[I] Reset Qdrant storage (backup first)…"
mkdir -p ~/qdrant_backup ~/qdrant/qdrant_storage
if [ -d ~/qdrant/qdrant_storage ] && [ "$(ls -A ~/qdrant/qdrant_storage || true)" ]; then
  TS=$(date +%Y%m%d_%H%M%S)
  tar -C ~/qdrant -czf ~/qdrant_backup/qdrant_storage_${TS}.tgz qdrant_storage || true
fi
rm -rf ~/qdrant/qdrant_storage
mkdir -p ~/qdrant/qdrant_storage

echo "[I] Start Qdrant (GPU compose) on 6333/6334…"
cd ~/qdrant
docker compose up -d
sleep 3
curl -sf http://127.0.0.1:6333 >/dev/null || { echo "[X] Qdrant not responding on 6333"; exit 1; }

# --- 2) Create fresh collection + payload schema/indexes ---
echo "[I] Create collection ${COLLECTION} (dim=${EMBED_DIM}, distance=Cosine)…"
python - <<'PY'
import os, requests
Q=os.getenv("QDRANT_URL","http://127.0.0.1:6333")
COL=os.getenv("COLLECTION","mas_ingest_d768")
DIM=int(os.getenv("EMBED_DIM","768"))

def rq(method, path, **kw):
    r=requests.request(method, Q+path, timeout=30, **kw); r.raise_for_status(); return r

# Create/overwrite collection
rq("PUT", f"/collections/{COL}", json={
  "vectors": {"size": DIM, "distance": "Cosine"},
  "hnsw_config": {"m": 32, "ef_construct": 256, "payload_m": 16},
  "optimizers_config": {"default_segment_number": 6},
  "on_disk_payload": True
})

# Schema + indexes for fast filters
schema = {
  "case": {"type": "keyword"},
  "modality": {"type": "keyword"},
  "mime": {"type": "keyword"},
  "ts_month": {"type": "keyword"},
  "source_path": {"type": "text"}
}
try:
    rq("PATCH", f"/collections/{COL}/payload-schema", json=schema)
except Exception:
    pass

for fld in ["case","modality","mime","ts_month"]:
    rq("PUT", f"/collections/{COL}/indexes/{fld}", json={"field_name": fld, "field_schema": "keyword"})

print(f"[OK] Collection {COL} is ready.")
PY

# --- 3) Start API/workers via systemd (they'll auto-restart on failure) ---
echo "[I] Starting API + workers (systemd user)…"
cd ~/mas-v2-consolidated
systemctl --user daemon-reload || true
systemctl --user start masv2-api masv2-workers
sleep 3
curl -s -o /dev/null -w "[I] API /metrics -> HTTP %{http_code}\n" "http://127.0.0.1:${UVICORN_PORT}/metrics" || true

# --- 4) Auto-tagger: derive case/modality/mime/ts_month and keep tagging new points ---
echo "[I] Launching background auto-tagger to enrich payloads…"
nohup python - <<'PY' >/tmp/mas_autotagger.log 2>&1 &
import os, time, mimetypes, requests, datetime, re
Q=os.getenv("QDRANT_URL","http://127.0.0.1:6333")
COL=os.getenv("COLLECTION","mas_ingest_d768")

def rq(method, path, **kw):
    return requests.request(method, Q+path, timeout=60, **kw)

def infer_case(path):
    if path.startswith("/home/starlord/raycastfiles/Life"): return "Life"
    if "/mas-v2-crewai/cases_to_process/Metro" in path: return "Metro"
    m=re.search(r"/mas-v2-crewai/cases_to_process/([^/]+)", path) or re.search(r"/cases_to_process/([^/]+)", path)
    return m.group(1) if m else "unknown"

def infer_modality(path, text_preview):
    p=path.lower()
    if any(p.endswith(ext) for ext in [".jpg",".jpeg",".png",".gif",".webp",".tif",".tiff",".bmp",".heic"]): return "image"
    if any(p.endswith(ext) for ext in [".mp4",".mov",".avi",".mkv",".webm",".m4v"]): return "video"
    if any(p.endswith(ext) for ext in [".mp3",".wav",".m4a",".flac",".aac",".ogg"]): return "audio"
    if any(p.endswith(ext) for ext in [".pdf",".doc",".docx",".ppt",".pptx",".xls",".xlsx",".txt",".csv",".md",".rtf",".xml",".json",".yaml",".yml"]): return "document"
    if any(x in p for x in ["officefilecache","outlook","onenote","teams","wef","inetcache","roamcache","olk","content.outlook"]): return "ms_artifact"
    if any(p.endswith(ext) for ext in [".pst",".ost",".olm"]): return "mail_store"
    return "unknown"

def infer_mime(path):
    mime,_=mimetypes.guess_type(path)
    return mime or "application/octet-stream"

def month_stamp():
    now=datetime.datetime.utcnow()
    return f"{now.year}-{now.month:02d}"

def needs_tags(payload):
    return not all(k in payload for k in ("case","modality","mime","ts_month"))

def update_payload(updates):
    if updates:
        rq("POST", f"/collections/{COL}/points/payload", json={"points": updates}).raise_for_status()

def run_pass(limit=2048):
    offset=None; updated=0
    while True:
        r=rq("POST", f"/collections/{COL}/points/scroll",
             json={"limit": 256, "offset": offset, "with_payload": True, "with_vectors": False})
        data=r.json().get("result") or {}
        pts=data.get("points",[])
        offset=data.get("next_page_offset")
        if not pts: break
        patch=[]
        for pt in pts:
            p=pt.get("payload") or {}
            if not needs_tags(p): continue
            sp=p.get("source_path") or p.get("file_path") or ""
            payload={**p,
              "case": p.get("case") or infer_case(sp),
              "modality": p.get("modality") or infer_modality(sp, p.get("text") or ""),
              "mime": p.get("mime") or infer_mime(sp),
              "ts_month": p.get("ts_month") or month_stamp()
            }
            patch.append({"id": pt["id"], "payload": payload})
            if len(patch)>=128:
                update_payload(patch); updated+=len(patch); patch=[]
        if patch: update_payload(patch); updated+=len(patch)
        if updated>=limit: break
    return updated

while True:
    try:
        run_pass(limit=5000)
        time.sleep(30)
    except Exception:
        time.sleep(10)
PY
disown || true
echo "[tagger] running (logs: /tmp/mas_autotagger.log)"

# --- 5) Helper: quick count function ---
count() { curl -s -X POST "${QDRANT_URL}/collections/${COLLECTION}/points/count" \
  -H 'Content-Type: application/json' -d '{"exact":true}' | jq -r '.result.count // 0'; }

echo "[I] Qdrant points in ${COLLECTION}: $(count)"

# --- 6) Ingest order: Life → Metro → the rest (top-level dirs under ROOT, excluding Metro) ---
API="http://127.0.0.1:${UVICORN_PORT}"

if [ -d "${LIFE_DIR}" ]; then
  echo "[I] Enqueue 1/3: LIFE -> ${LIFE_DIR}"
  curl -s -X POST "${API}/ingest_folder" -H "Content-Type: application/json" \
    -d "{\"remote_folder_path\":\"${LIFE_DIR}\",\"collection\":\"${COLLECTION}\"}" | jq .
else
  echo "[W] Life directory not found: ${LIFE_DIR}"
fi

echo "[I] Watch counts for 2 minutes (every 10s)…"
for i in {1..12}; do echo "  points=$(count) @ $(date +%H:%M:%S)"; sleep 10; done

if [ -d "${METRO_DIR}" ]; then
  echo "[I] Enqueue 2/3: METRO -> ${METRO_DIR}"
  curl -s -X POST "${API}/ingest_folder" -H "Content-Type: application/json" \
    -d "{\"remote_folder_path\":\"${METRO_DIR}\",\"collection\":\"${COLLECTION}\"}" | jq .
else
  echo "[W] Metro directory not found: ${METRO_DIR}"
fi

echo "[I] Watch counts for 2 minutes (every 10s)…"
for i in {1..12}; do echo "  points=$(count) @ $(date +%H:%M:%S)"; sleep 10; done

if [ -d "${ROOT_DIR}" ]; then
  echo "[I] Discover remaining top-level folders under ${ROOT_DIR} (excluding Metro)…"
  mapfile -t REST < <(find "${ROOT_DIR}" -maxdepth 1 -mindepth 1 -type d ! -name "Metro" | sort)
  printf '%s\n' "${REST[@]}"
  echo "[I] Enqueue 3/3: the rest…"
  for d in "${REST[@]}"; do
    echo "  -> $d"
    curl -s -X POST "${API}/ingest_folder" -H "Content-Type: application/json" \
      -d "{\"remote_folder_path\":\"${d}\",\"collection\":\"${COLLECTION}\"}" | jq -r '.status // .ok // .detail // "queued"'
    sleep 1
  done
else
  echo "[W] cases_to_process not found: ${ROOT_DIR}"
fi

echo "[✓] Queued: Life → Metro → rest. Auto-tagger running (logs: /tmp/mas_autotagger.log)."
echo "[→] Quick checks:"
echo "    - API:     curl -s http://127.0.0.1:${UVICORN_PORT}/metrics | head -1"
echo "    - Count:   curl -s -X POST ${QDRANT_URL}/collections/${COLLECTION}/points/count -H 'Content-Type: application/json' -d '{\"exact\":true}' | jq"
echo "    - Tagger:  tail -f /tmp/mas_autotagger.log"