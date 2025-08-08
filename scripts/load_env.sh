#!/usr/bin/env bash
# Load environment variables from .env file

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-$SCRIPT_DIR/../.env}"

if [ -f "$ENV_FILE" ]; then
    # Export all non-comment lines from .env
    set -a
    source "$ENV_FILE"
    set +a
    echo "Environment loaded from: $ENV_FILE" >&2
else
    echo "Warning: $ENV_FILE not found" >&2
fi