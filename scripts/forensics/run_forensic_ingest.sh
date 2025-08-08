#!/usr/bin/env bash
. "$(dirname "$0")/forensics/ensure_venv.sh"
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.."; pwd)"
ROOT="${1:?usage: run_forensic_ingest.sh /path/to/folder}"
cd "$REPO"

# Ensure ports/services are clean before proceeding
AUTO_FIX=1 ./scripts/ports_guard.sh

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
