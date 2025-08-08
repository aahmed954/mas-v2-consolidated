#!/usr/bin/env bash
# === starlord_qdrant_setup.sh ===
# Sets up Qdrant (latest stable CPU), ensures clean single container, verifies JSON,
# installs an auto-detecting system check (search vs query), and runs it once.

set -euo pipefail

QDRANT_NAME="masv2-qdrant"
QDRANT_TAG="${QDRANT_TAG:-v1.15.1}"          # pin a known-good stable; change to 'latest' if you really want rolling
QDRANT_IMAGE="qdrant/qdrant:${QDRANT_TAG}"
QDRANT_HTTP="http://localhost:6333"
QDRANT_GRPC="6334"
QDRANT_STORAGE="/home/starlord/qdrant_storage"

REPO_DIR="$HOME/mas-v2-consolidated"
CHECK_SCRIPT="$REPO_DIR/scripts/checks/full_system_check.sh"

echo "== 1) Ensure storage exists =="
mkdir -p "$QDRANT_STORAGE"
chmod 700 "$QDRANT_STORAGE"

echo "== 2) Stop/remove any existing Qdrant on 6333/6334 =="
docker rm -f "$QDRANT_NAME" >/dev/null 2>&1 || true

echo "== 3) Pull & run Qdrant (${QDRANT_IMAGE}) (CPU image, no GPU flags) =="
docker pull "$QDRANT_IMAGE"
docker run -d --name "$QDRANT_NAME" \
  --restart unless-stopped \
  -p 6333:6333 -p 6334:6334 \
  -v "$QDRANT_STORAGE":/qdrant/storage \
  "$QDRANT_IMAGE"

echo "== 4) Wait for Qdrant JSON root & /metrics =="
for i in {1..20}; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "$QDRANT_HTTP" || true)
  [[ "$code" == "200" ]] && break
  sleep 0.5
done
[[ "$code" == "200" ]] || { echo "❌ Qdrant root not ready (HTTP $code)"; exit 1; }

curl -s "$QDRANT_HTTP" | head -n 1 >/dev/null || { echo "❌ No JSON from root"; exit 1; }
curl -s "$QDRANT_HTTP/metrics" | head -n 3 >/dev/null || { echo "❌ No /metrics"; exit 1; }
echo "✅ Qdrant is up @ $QDRANT_HTTP"

echo "== 5) Install/refresh auto-detecting system check =="
mkdir -p "$REPO_DIR/scripts/checks"

cat > "$CHECK_SCRIPT" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
COLLECTION="${COLLECTION:-mas_embeddings}"
MODEL_ID="${MODEL_ID:-BAAI/bge-base-en-v1.5-vllm}"
DIM_EXPECTED="${DIM_EXPECTED:-768}"
DISTANCE_EXPECTED="${DISTANCE_EXPECTED:-Cosine}"
TOGETHER_BASE_URL="${TOGETHER_BASE_URL:-https://api.together.xyz/v1}"

pass(){ echo "✅ $*"; }
fail(){ echo "❌ $*"; exit 1; }

[[ -n "${TOGETHER_API_KEY:-}" ]] || fail "TOGETHER_API_KEY not set"

# Health (prefer /ready, else root)
http_code=$(curl -s -o /dev/null -w '%{http_code}' "$QDRANT_URL/ready" || true)
[[ "$http_code" == "200" ]] || http_code=$(curl -s -o /dev/null -w '%{http_code}' "$QDRANT_URL/" || true)
[[ "$http_code" == "200" ]] || fail "Qdrant not healthy ($http_code)"
pass "Qdrant is ready ($QDRANT_URL)"

curl -s "$QDRANT_URL/metrics" | head -n 1 >/dev/null || fail "Qdrant /metrics missing"
pass "Qdrant /metrics responding"

# TogetherAI embedding
emb_json=$(curl -s -X POST "$TOGETHER_BASE_URL/embeddings" \
  -H "Authorization: Bearer $TOGETHER_API_KEY" \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg m "$MODEL_ID" --arg txt "system check hello world" '{model:$m, input:[$txt], encoding_format:"float"}')")

err_msg=$(echo "$emb_json" | jq -r '.error?.message // empty' 2>/dev/null || true)
[[ -z "$err_msg" ]] || fail "Together embeddings error: $err_msg"

dim=$(echo "$emb_json" | jq -r '.data[0].embedding | length')
[[ "$dim" == "$DIM_EXPECTED" ]] || fail "Embedding dim $dim != expected $DIM_EXPECTED"
pass "Together embeddings OK: $MODEL_ID → $dim dims"

# Ensure collection
info_json=$(curl -s "$QDRANT_URL/collections/$COLLECTION" || true)
exists=$(echo "$info_json" | jq -r '.status // empty')
if [[ "$exists" != "ok" ]]; then
  create_body=$(jq -n --argjson size "$DIM_EXPECTED" --arg dist "$DISTANCE_EXPECTED" '{vectors:{size:$size, distance:$dist}}')
  curl -s -X PUT "$QDRANT_URL/collections/$COLLECTION" -H "Content-Type: application/json" -d "$create_body" >/dev/null
  info_json=$(curl -s "$QDRANT_URL/collections/$COLLECTION")
fi

size=$(echo "$info_json" | jq -r '.result.config.params.vectors.size // .result.config.params.vectors.params.size // empty')
dist=$(echo "$info_json" | jq -r '.result.config.params.vectors.distance // .result.config.params.vectors.params.distance // empty')
[[ "$size" == "$DIM_EXPECTED" ]] || fail "Collection dim $size != expected $DIM_EXPECTED"
[[ "${dist,,}" == "cosine" ]] || fail "Collection distance $dist != expected Cosine"
pass "Collection $COLLECTION schema OK ($size / $dist)"

# Prepare vector + id
vec=$(echo "$emb_json" | jq -c '.data[0].embedding')
pid=$(uuidgen 2>/dev/null || python3 - <<'PY'
import uuid; print(uuid.uuid4())
PY
)

upsert_body=$(jq -n --arg id "$pid" --argjson v "$vec" --arg txt "system check hello world" \
  '{points:[{id:$id, vector:$v, payload:{kind:"system_check", text:$txt}}]}')

# Upsert (task envelope)
upsert_resp=$(curl -s -X PUT "$QDRANT_URL/collections/$COLLECTION/points?wait=true" \
  -H "Content-Type: application/json" -d "$upsert_body")
up_status=$(echo "$upsert_resp" | jq -r '.status // empty')
[[ "$up_status" == "ok" ]] || fail "Upsert failed: $upsert_resp"

# Verify by ID
get_by_id=$(jq -n --arg id "$pid" '{ids:[$id]}')
got=$(curl -s -X POST "$QDRANT_URL/collections/$COLLECTION/points" \
  -H "Content-Type: application/json" -d "$get_by_id")
present=$(echo "$got" | jq -r --arg id "$pid" '[.result[]?.id==$id] | any')
[[ "$present" == "true" ]] || fail "Point not retrievable by ID: $got"
pass "Point present by ID"

# Decide API: try to read server version and choose query path accordingly
root_json=$(curl -s "$QDRANT_URL/")
qv=$(echo "$root_json" | jq -r '.version // empty')
use_query_api=0
if [[ -n "$qv" ]]; then
  major=$(echo "$qv" | cut -d. -f1); minor=$(echo "$qv" | cut -d. -f2)
  if [[ "$major" -ge 2 || "$minor" -ge 16 ]]; then use_query_api=1; fi
fi

if [[ "$use_query_api" -eq 1 ]]; then
  query_body=$(jq -n --argjson v "$vec" '{query:{nearest:{vector:$v}},limit:5,with_payload:true}')
  hits=$(curl -s -X POST "$QDRANT_URL/collections/$COLLECTION/points/query" \
    -H "Content-Type: application/json" -d "$query_body")
  found=$(echo "$hits" | jq -r --arg id "$pid" '[ .result.points[]?.id == $id ] | any')
else
  search_body=$(jq -n --argjson v "$vec" '{vector:$v, limit:5, with_payload:true}')
  hits=$(curl -s -X POST "$QDRANT_URL/collections/$COLLECTION/points/search" \
    -H "Content-Type: application/json" -d "$search_body")
  found=$(echo "$hits" | jq -r --arg id "$pid" '[ .result[]?.id == $id ] | any')
fi

if [[ "$found" != "true" ]]; then
  echo "Search miss; hits were:" >&2
  echo "$hits" | jq '.result' >&2
  scroll_body='{"filter":{"must":[{"key":"kind","match":{"value":"system_check"}}]},"with_payload":true,"limit":5}'
  scroll=$(curl -s -X POST "$QDRANT_URL/collections/$COLLECTION/points/scroll" \
    -H "Content-Type: application/json" -d "$scroll_body")
  echo "Scroll sample:" >&2
  echo "$scroll" | jq '.result.points // .result' >&2
  fail "Search did not find the test point"
fi
pass "Vector query found test point ✔"

# Count
count_json=$(curl -s -X POST "$QDRANT_URL/collections/$COLLECTION/points/count" \
  -H "Content-Type: application/json" -d '{"exact":true}')
count=$(echo "$count_json" | jq -r '.result.count')
[[ -n "$count" ]] || fail "Count endpoint failed"
pass "Count endpoint responding (collection count: $count)"

# Cleanup temp point
curl -s -X POST "$QDRANT_URL/collections/$COLLECTION/points/delete?wait=true" \
  -H "Content-Type: application/json" -d "{\"points\":[\"$pid\"]}" >/dev/null
pass "Temp point cleaned up"

echo "-------------------------------------------"
echo "ALL CHECKS PASSED for collection: $COLLECTION"
echo "Qdrant: $QDRANT_URL   |  Metrics: $QDRANT_URL/metrics"
echo "Together model: $MODEL_ID (dim $DIM_EXPECTED)"
SH
chmod +x "$CHECK_SCRIPT"

echo "== 6) Run the check once (reads TOGETHER_API_KEY from env) =="
if [[ -z "${TOGETHER_API_KEY:-}" ]]; then
  echo "⚠️  TOGETHER_API_KEY not in this shell. Export it and re-run the check:"
  echo "    export TOGETHER_API_KEY='tgp_...'; $CHECK_SCRIPT"
else
  "$CHECK_SCRIPT"
fi

echo "== Done =="