#!/usr/bin/env bash
set -euo pipefail
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
COLLECTION="${COLLECTION:-mas_embeddings}"
MODEL_ID="${MODEL_ID:-BAAI/bge-base-en-v1.5-vllm}"
DIM_EXPECTED="${DIM_EXPECTED:-768}"
DISTANCE_EXPECTED="${DISTANCE_EXPECTED:-Cosine}"
TOGETHER_BASE_URL="${TOGETHER_BASE_URL:-https://api.together.xyz/v1}"
pass(){ echo "✅ $*"; } ; fail(){ echo "❌ $*"; exit 1; }
[[ -n "${TOGETHER_API_KEY:-}" ]] || fail "TOGETHER_API_KEY not set"

# Health (prefer /ready, else root)
code=$(curl -s -o /dev/null -w '%{http_code}' "$QDRANT_URL/ready" || true)
[[ "$code" == "200" ]] || code=$(curl -s -o /dev/null -w '%{http_code}' "$QDRANT_URL/" || true)
[[ "$code" == "200" ]] || fail "Qdrant not healthy ($code)"
pass "Qdrant ready ($QDRANT_URL)"; curl -s "$QDRANT_URL/metrics" | head -n1 >/dev/null || fail "/metrics missing"; pass "Qdrant /metrics ok"

# Together → 768 dims
emb_json=$(curl -s -X POST "$TOGETHER_BASE_URL/embeddings" -H "Authorization: Bearer $TOGETHER_API_KEY" -H "Content-Type: application/json" -d "$(jq -n --arg m "$MODEL_ID" --arg t "system check hello world" '{model:$m, input:[$t], encoding_format:"float"}')")
[[ -z "$(echo "$emb_json" | jq -r '.error?.message // empty')" ]] || fail "Together: $(echo "$emb_json" | jq -r '.error.message')"
dim=$(echo "$emb_json" | jq -r '.data[0].embedding | length')
[[ "$dim" == "$DIM_EXPECTED" ]] || fail "Embedding dim $dim != $DIM_EXPECTED"; pass "Together OK: $MODEL_ID → $dim"

# Ensure collection 768/Cosine
info=$(curl -s "$QDRANT_URL/collections/$COLLECTION" || true)
if [[ "$(echo "$info" | jq -r '.status // empty')" != "ok" ]]; then
  curl -s -X PUT "$QDRANT_URL/collections/$COLLECTION" -H "Content-Type: application/json" -d "$(jq -n --argjson s "$DIM_EXPECTED" --arg d "$DISTANCE_EXPECTED" '{vectors:{size:$s,distance:$d}}')" >/dev/null
  info=$(curl -s "$QDRANT_URL/collections/$COLLECTION")
fi
size=$(echo "$info" | jq -r '.result.config.params.vectors.size // .result.config.params.vectors.params.size // empty')
dist=$(echo "$info" | jq -r '.result.config.params.vectors.distance // .result.config.params.vectors.params.distance // empty')
[[ "$size" == "$DIM_EXPECTED" ]] || fail "Collection dim $size != $DIM_EXPECTED"
[[ "${dist,,}" == "cosine" ]] || fail "Collection distance $dist != Cosine"; pass "Schema OK ($size/$dist)"

vec=$(echo "$emb_json" | jq -c '.data[0].embedding')
pid=$(uuidgen 2>/dev/null || python3 -c "import uuid;print(uuid.uuid4())")
upsert=$(jq -n --arg id "$pid" --argjson v "$vec" --arg txt "system check hello world" '{points:[{id:$id, vector:$v, payload:{kind:"system_check", text:$txt}}]}')
resp=$(curl -s -X PUT "$QDRANT_URL/collections/$COLLECTION/points?wait=true" -H "Content-Type: application/json" -d "$upsert")
[[ "$(echo "$resp" | jq -r '.status // empty')" == "ok" ]] || fail "Upsert failed: $resp"

# Verify by ID
get=$(curl -s -X POST "$QDRANT_URL/collections/$COLLECTION/points" -H "Content-Type: application/json" -d "$(jq -n --arg id "$pid" '{ids:[$id]}')")
[[ "$(echo "$get" | jq -r --arg id "$pid" '[.result[]?.id==$id] | any')" == "true" ]] || fail "Point not retrievable by ID"; pass "Point present by ID"

# Auto select query API by version
root=$(curl -s "$QDRANT_URL/"); qv=$(echo "$root" | jq -r '.version // empty'); use_query=0
if [[ -n "$qv" ]]; then maj=$(echo "$qv" | cut -d. -f1); min=$(echo "$qv" | cut -d. -f2); [[ "$maj" -ge 2 || "$min" -ge 16 ]] && use_query=1; fi
if [[ "$use_query" -eq 1 ]]; then
  hits=$(curl -s -X POST "$QDRANT_URL/collections/$COLLECTION/points/query" -H "Content-Type: application/json" -d "$(jq -n --argjson v "$vec" '{query:{nearest:{vector:$v}},limit:5,with_payload:true}')")
  found=$(echo "$hits" | jq -r --arg id "$pid" '[.result.points[]?.id==$id] | any')
else
  hits=$(curl -s -X POST "$QDRANT_URL/collections/$COLLECTION/points/search" -H "Content-Type: application/json" -d "$(jq -n --argjson v "$vec" '{vector:$v, limit:5, with_payload:true}')")
  found=$(echo "$hits" | jq -r --arg id "$pid" '[.result[]?.id==$id] | any')
fi
[[ "$found" == "true" ]] || { echo "$hits" | jq '.result' >&2; fail "Search did not find test point"; }
pass "Vector query found test point"

# Count + cleanup
count=$(curl -s -X POST "$QDRANT_URL/collections/$COLLECTION/points/count" -H "Content-Type: application/json" -d '{"exact":true}' | jq -r '.result.count')
[[ -n "$count" ]] || fail "Count failed"; pass "Count ok ($count)"
curl -s -X POST "$QDRANT_URL/collections/$COLLECTION/points/delete?wait=true" -H "Content-Type: application/json" -d "{\"points\":[\"$pid\"]}" >/dev/null
pass "Temp point cleaned"
echo "ALL CHECKS PASSED ($COLLECTION)"
