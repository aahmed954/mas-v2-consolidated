#!/usr/bin/env python3
"""
Registry extractor for Windows drive copies.
Finds system/user hives in a mounted copy and exports:
- JSONL full traversals per hive (selective to avoid explosions)
- Targeted keys (MRUs, Office Resiliency, OutlookSecureTempFolder, RecentDocs, UserAssist, TypedURLs, Run, Installed Apps)
- Human-readable summaries for embedding

Outputs to artifact_dump/registry/
"""
import os, sys, json, re, hashlib
from pathlib import Path
from datetime import datetime
from regipy.registry import RegistryHive
from regipy.exceptions import RegistryKeyNotFoundException

ROOT = Path(sys.argv[1] if len(sys.argv)>1 else ".").resolve()
OUT  = Path(sys.argv[2] if len(sys.argv)>2 else "artifact_dump/registry").resolve()
OUT.mkdir(parents=True, exist_ok=True)

# Common hive names/locations inside a disk copy
HIVE_CANDIDATES = [
    # SYSTEM-wide
    r"Windows\\System32\\config\\SAM",
    r"Windows\\System32\\config\\SECURITY",
    r"Windows\\System32\\config\\SOFTWARE",
    r"Windows\\System32\\config\\SYSTEM",
    # User hives
    r"Users\\[^\\]+\\NTUSER\.DAT",
    r"Users\\[^\\]+\\AppData\\Local\\Microsoft\\Windows\\UsrClass\.dat",
]

TARGETS = {
    # Office crash/recovery & resiliency
    ("HKCU","Software\\Microsoft\\Office\\16.0\\Common\\Resiliency"): "office_resiliency",
    # Outlook OLK temp path (attachment cache)
    ("HKCU","Software\\Microsoft\\Office\\16.0\\Outlook\\Security"): "outlook_security",
    # Office MRU lists
    ("HKCU","Software\\Microsoft\\Office\\Common\\Open Find\\Microsoft Office Word\\Settings\\File MRU"): "word_mru",
    ("HKCU","Software\\Microsoft\\Office\\Common\\Open Find\\Microsoft Office Excel\\Settings\\File MRU"): "excel_mru",
    ("HKCU","Software\\Microsoft\\Office\\Common\\Open Find\\Microsoft Office PowerPoint\\Settings\\File MRU"): "ppt_mru",
    # Explorer recent docs
    ("HKCU","Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\RecentDocs"): "recent_docs",
    # UserAssist (program execution)
    ("HKCU","Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\UserAssist"): "userassist",
    # Typed URLs
    ("HKCU","Software\\Microsoft\\Internet Explorer\\TypedURLs"): "typed_urls",
    # Run keys (persistence)
    ("HKCU","Software\\Microsoft\\Windows\\CurrentVersion\\Run"): "run_user",
    ("HKLM","SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run"): "run_machine",
    # Installed apps (uninstall)
    ("HKLM","SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall"): "uninstall",
    # Network/history bits
    ("HKCU","Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\MountPoints2"): "mountpoints2",
}

def hive_kind_from_path(p: Path):
    s = str(p).lower()
    if s.endswith(("sam","security","software","system")): return "HKLM"
    if s.endswith(("ntuser.dat", "usrclass.dat")): return "HKCU"
    return "UNK"

def safe_json(obj):
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return json.dumps(str(obj), ensure_ascii=False)

def dump_key(hive: RegistryHive, root_path: str):
    try:
        key = hive.get_key(root_path)
    except RegistryKeyNotFoundException:
        return None
    out = {
        "path": root_path,
        "last_written": key.header.last_modified.isoformat() if key.header and hasattr(key.header.last_modified, 'isoformat') else str(key.header.last_modified) if key.header and key.header.last_modified else None,
        "values": {},
        "subkeys": [sk.name for sk in key.iter_subkeys()]  # names only to keep size sane
    }
    # values
    for v in key.iter_values():
        out["values"][v.name or "(Default)"] = v.value
    return out

def summarize_target(name: str, data):
    # Minimal human-readable summary
    lines = [f"# {name}"]
    if not data:
        lines.append("Not found.")
        return "\n".join(lines)
    lines.append(f"Key: {data.get('path')}")
    lines.append(f"LastWrite: {data.get('last_written')}")
    vals = data.get("values",{})
    if vals:
        lines.append("Values:")
        for k,v in vals.items():
            s = str(v)
            s = s[:2000] + ("..." if len(s)>2000 else "")
            lines.append(f"  - {k}: {s}")
    return "\n".join(lines)

def write(path: Path, name: str, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8', errors='ignore')

def main():
    results = []
    # Find hives
    hives = []
    for dp,_,files in os.walk(ROOT):
        for fn in files:
            full = Path(dp)/fn
            rel = full.relative_to(ROOT)
            s = str(rel).replace('/', '\\')
            if any(re.search(pat, s, flags=re.IGNORECASE) for pat in HIVE_CANDIDATES):
                hives.append((full, rel))
    # Deduplicate identical hives by SHA256
    seen = {}
    for full, rel in hives:
        try:
            import hashlib
            h = hashlib.sha256(open(full,'rb').read(1024*1024)).hexdigest()  # quick hash on first 1MB
            if h in seen: continue
            seen[h] = (full, rel)
        except Exception: pass
    hives = list(seen.values())
    # Process
    for full, rel in hives:
        kind = hive_kind_from_path(full)
        out_dir = OUT / rel.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        meta = {"hive": str(rel), "kind": kind}
        try:
            hive = RegistryHive(str(full))
        except Exception as e:
            meta["error"] = str(e)
            write(out_dir/ (rel.name+".error.txt"), str(rel), str(e))
            results.append(meta)
            continue

        # Targeted keys
        targeted = {}
        for (scope, key_path), label in TARGETS.items():
            if scope != kind:  # naive scope match
                continue
            data = dump_key(hive, key_path)
            targeted[label] = data
            # Specific extraction: OutlookSecureTempFolder in outlook_security
            if label == "outlook_security" and data and "values" in data:
                ostf = data["values"].get("OutlookSecureTempFolder")
                if ostf:
                    targeted["outlook_secure_temp_folder"] = ostf

        # Write per-hive JSON + summary
        jpath = out_dir / (rel.name + ".targets.json")
        tpath = out_dir / (rel.name + ".targets.txt")
        write(jpath, jpath.name, json.dumps(targeted, indent=2, ensure_ascii=False))
        # Simple text summary for embeddings
        parts = []
        for label, data in targeted.items():
            parts.append(summarize_target(label, data))
        write(tpath, tpath.name, "\n\n".join(parts))

        # Record
        meta["targets_path_json"] = str(jpath.relative_to(OUT.parent))
        meta["targets_path_txt"]  = str(tpath.relative_to(OUT.parent))
        results.append(meta)

    # Write index
    idx = OUT / "_registry_index.json"
    write(idx, idx.name, json.dumps({"root": str(ROOT), "processed": results}, indent=2, ensure_ascii=False))
    print(json.dumps({"processed_hives": len(results), "out": str(OUT)}, indent=2))

if __name__ == "__main__":
    main()