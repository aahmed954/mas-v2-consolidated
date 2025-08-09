#!/usr/bin/env bash
set -euo pipefail
if [ -f ".env" ]; then
  set -a
  . ./.env
  set +a
else
  echo "[load_env] .env missing in $(pwd)" >&2
  exit 1
fi
