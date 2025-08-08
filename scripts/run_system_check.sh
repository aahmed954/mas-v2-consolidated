#!/usr/bin/env bash
# Run system check with proper environment

# Load environment variables
. "$(dirname "$0")/load_env.sh"

# Run the system check
if [ -z "${TOGETHER_API_KEY}" ]; then
    echo "❌ TOGETHER_API_KEY not set" >&2
    exit 1
fi

if [ -z "${CONTROL_API_KEY}" ]; then
    echo "❌ CONTROL_API_KEY not set" >&2
    exit 1
fi

# Run via control API
curl -s "http://localhost:8088/system-check/run?key=${CONTROL_API_KEY}" | jq .