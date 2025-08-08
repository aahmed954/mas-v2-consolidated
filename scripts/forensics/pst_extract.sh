#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-/data}"
OUT="${2:-artifact_dump/pst}"
mkdir -p "$OUT"
shopt -s globstar nullglob
for pst in "$ROOT"/**/*.pst; do
  base=$(basename "$pst" .pst)
  dir="$OUT/${base}"
  mkdir -p "$dir"
  if command -v readpst >/dev/null 2>&1; then
    readpst -r -o "$dir" "$pst" || true
  fi
  # crude text pass (strings)
  strings "$pst" | head -n 100000 > "$dir/${base}.strings.txt" || true
done