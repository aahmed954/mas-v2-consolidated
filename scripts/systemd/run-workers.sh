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
for i in 1 2 3 4; do
    python -m rq.cli worker high_throughput &
done
wait
