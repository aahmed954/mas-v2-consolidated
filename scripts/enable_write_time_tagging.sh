#!/bin/bash
# === MASv2: enable write-time auto-tagging (case/modality/mime/ts_month) ===
set -euo pipefail
cd ~/mas-v2-consolidated
source .venv/bin/activate 2>/dev/null || source ~/.venvs/masv2/bin/activate
export PYTHONPATH=$PWD

# 1) Create the router
cat > src/payload_router.py <<'PY'
import re, mimetypes
from datetime import datetime

def _derive_case(path: str) -> str:
    if path.startswith("/home/starlord/raycastfiles/Life"):
        return "Life"
    if "/mas-v2-crewai/cases_to_process/Metro" in path:
        return "Metro"
    m = re.search(r"/mas-v2-crewai/cases_to_process/([^/]+)", path) or re.search(r"/cases_to_process/([^/]+)", path)
    return m.group(1) if m else "Unsorted"

def _derive_modality(path: str, text: str | None) -> str:
    p = path.lower()
    if any(p.endswith(ext) for ext in (".jpg",".jpeg",".png",".gif",".webp",".tif",".tiff",".bmp",".heic",".heif")):
        return "image"
    if any(p.endswith(ext) for ext in (".mp4",".mov",".avi",".mkv",".webm",".m4v")):
        return "video"
    if any(p.endswith(ext) for ext in (".mp3",".wav",".m4a",".flac",".aac",".ogg",".opus",".wma")):
        return "audio"
    if any(p.endswith(ext) for ext in (".pdf",".doc",".docx",".ppt",".pptx",".xls",".xlsx",".txt",".csv",".md",".rtf",".xml",".json",".yaml",".yml")):
        return "document"
    if any(x in p for x in ("officefilecache","outlook","onenote","teams","wef","inetcache","roamcache","olk","content.outlook")):
        return "ms_artifact"
    if any(p.endswith(ext) for ext in (".pst",".ost",".olm")):
        return "mail_store"
    return "text"

def _ts_month(path: str) -> str:
    m = re.search(r"(20\d{2})[-_\.]?(0[1-9]|1[0-2])", path)
    if m: return f"{m.group(1)}-{m.group(2)}"
    return datetime.utcnow().strftime("%Y-%m")

def route_payload(source_path: str, base_payload: dict | None, chunk_text: str | None = None) -> dict:
    p = dict(base_payload or {})
    p.setdefault("source_path", source_path)
    p.setdefault("case", _derive_case(source_path))
    p.setdefault("modality", _derive_modality(source_path, chunk_text))
    p.setdefault("mime", mimetypes.guess_type(source_path)[0] or "application/octet-stream")
    p.setdefault("ts_month", _ts_month(source_path))
    return p
PY

# 2) Patch src/forensic_worker.py (import + one-line enrich)
python - <<'PY'
import io, re, sys, pathlib
p = pathlib.Path("src/forensic_worker.py")
s = p.read_text()

# ensure import exists
if "from .payload_router import route_payload" not in s:
    # put import near other imports
    s = re.sub(r"(^from\s+qdrant_client\s+import\s+QdrantClient.*?$)",
               r"\1\nfrom .payload_router import route_payload",
               s, flags=re.M)

# after the first assignment to payload = { ... }, enrich with router
if "route_payload(" not in s:
    # find a 'payload = {' block and insert enrichment on next line
    s = re.sub(
        r"(payload\s*=\s*\{[^}]*\}\s*)",
        r"\1\n        payload = route_payload(source_path, payload, chunk_text)",
        s, count=1, flags=re.S
    )

pathlib.Path("src/forensic_worker.py").write_text(s)
print("[OK] forensic_worker.py patched")
PY

# (Optional) If you also build payloads in src/api_v2.py for any direct upserts, patch similarly:
if grep -q "payload =" src/api_v2.py 2>/dev/null; then
python - <<'PY'
import io, re, sys, pathlib
p = pathlib.Path("src/api_v2.py")
s = p.read_text()

if "from .payload_router import route_payload" not in s:
    s = re.sub(r"(^import\s+.+?$)", r"\1\nfrom .payload_router import route_payload", s, count=1, flags=re.M)

if "route_payload(" not in s and "payload =" in s:
    s = re.sub(
        r"(payload\s*=\s*\{[^}]*\}\s*)",
        r"\1\n        payload = route_payload(source_path, payload, chunk_text if 'chunk_text' in locals() else payload.get('text'))",
        s, count=1, flags=re.S
    )

pathlib.Path("src/api_v2.py").write_text(s)
print("[OK] api_v2.py patched (if applicable)")
PY
fi

# 3) Restart services so writes are tagged immediately
systemctl --user daemon-reload || true
systemctl --user restart masv2-api masv2-workers
sleep 2
curl -s -o /dev/null -w "API /metrics -> HTTP %{http_code}\n" http://127.0.0.1:8002/metrics || true

echo "✅ Write-time tagging enabled. New chunks will have case/modality/mime/ts_month on insert."
echo "Tip: old points can still be backfilled via the tagger you launched earlier (or rerun it)."