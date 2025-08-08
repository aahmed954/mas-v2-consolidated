#!/usr/bin/env bash
. "$(dirname "$0")/ensure_venv.sh"
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.."; pwd)"
ROOT="${1:?usage: run_forensic_ingest.sh /path/to/folder}"
cd "$REPO"

# Skip global ports guard here (Qdrant must remain up)
# AUTO_FIX=1 ./scripts/ports_guard.sh

# Wait for Qdrant to be healthy before proceeding
wait_qdrant() {
  local url="${QDRANT_URL:-http://localhost:6333}"
  echo "== Waiting for Qdrant at $url =="
  for i in {1..40}; do
    code=$(curl -s -o /dev/null -w '%{http_code}' "$url/" || true)
    if [ "$code" = "200" ]; then
      echo "Qdrant ready."
      return 0
    fi
    sleep 1
  done
  echo "Qdrant not ready after timeout." >&2
  exit 1
}
wait_qdrant

source ~/.venvs/masv2/bin/activate || true

echo "== Manifest =="
PYTHONPATH=. python scripts/forensics/hash_and_manifest.py "$ROOT" "manifest.jsonl"

echo "== Sign Manifest =="
./scripts/forensics/sign_manifest.sh "manifest.jsonl"

echo "== Microsoft artifacts =="
PYTHONPATH=. python scripts/forensics/extract_ms_artifacts.py "$ROOT" "artifact_dump"

echo "== Registry hives =="
PYTHONPATH=. python scripts/forensics/registry_extract.py "$ROOT" "artifact_dump/registry"

echo "== PST optional =="
scripts/forensics/pst_extract.sh "$ROOT" || true

echo "== OCR/Transcribe/Embed =="
bash -lc './final_launch.sh'

echo "== Generate Report =="
PYTHONPATH=. python scripts/forensics/generate_report.py "artifact_dump" "forensic_report.html"

echo "== Case Report =="
PYTHONPATH=. python scripts/forensics/build_case_report.py "." "CASE_REPORT.md"
