#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.."; pwd)"
ROOT="${1:?usage: run_forensic_ingest.sh /path/to/folder}"
cd "$REPO"
source ~/.venvs/masv2/bin/activate || true

echo "== Manifest =="
PYTHONPATH=. python scripts/forensics/hash_and_manifest.py "$ROOT" "manifest.jsonl"

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