#!/usr/bin/env bash
# Check if all required environment variables are set

echo "=== MAS V2 Environment Check ==="
echo

# Load environment
. "$(dirname "$0")/load_env.sh"
echo

# Required variables
REQUIRED_VARS=(
    "CONTROL_API_KEY"
    "TOGETHER_API_KEY"
    "QDRANT_URL"
    "TOGETHER_BASE_URL"
    "TOGETHER_EMBEDDING_MODEL"
)

# Optional but recommended
OPTIONAL_VARS=(
    "REDIS_HOST"
    "REDIS_PORT"
    "LOCAL_EMBED_URL"
    "MAX_PARALLEL"
    "CPU_HIGH_WATER"
    "GPU_HIGH_WATER"
)

echo "Required Variables:"
echo "-----------------"
all_set=true
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ $var: NOT SET"
        all_set=false
    else
        # Mask sensitive values
        if [[ "$var" =~ KEY$ ]]; then
            value="${!var:0:10}..."
        else
            value="${!var}"
        fi
        echo "✅ $var: $value"
    fi
done

echo
echo "Optional Variables:"
echo "------------------"
for var in "${OPTIONAL_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        echo "⚠️  $var: not set (using default)"
    else
        echo "✅ $var: ${!var}"
    fi
done

echo
echo "Service Status:"
echo "--------------"
# Check services
if curl -s http://localhost:6333 >/dev/null 2>&1; then
    echo "✅ Qdrant: Running"
else
    echo "❌ Qdrant: Not responding"
fi

if curl -s http://localhost:8085/health >/dev/null 2>&1; then
    echo "✅ Local Embeddings: Running"
else
    echo "⚠️  Local Embeddings: Not running (failover available)"
fi

if curl -s http://localhost:8088/health >/dev/null 2>&1; then
    echo "✅ Control API: Running"
else
    echo "❌ Control API: Not responding"
fi

echo
if [ "$all_set" = true ]; then
    echo "✅ All required environment variables are set!"
else
    echo "❌ Some required variables are missing. Check .env file."
    exit 1
fi