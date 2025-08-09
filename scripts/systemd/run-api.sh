#!/bin/bash
set -e
cd /home/starlord/mas-v2-consolidated
if [ -f .venv/bin/activate ]; then
    . .venv/bin/activate
elif [ -f ~/.venvs/masv2/bin/activate ]; then
    . ~/.venvs/masv2/bin/activate
fi
if [ -f ./scripts/load_env.sh ]; then
    . ./scripts/load_env.sh
fi
exec python -m uvicorn src.api_v2:app --host "${UVICORN_HOST:-0.0.0.0}" --port "${UVICORN_PORT:-8002}"
