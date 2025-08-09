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
