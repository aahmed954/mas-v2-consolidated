#!/usr/bin/env python3
import os, sys, json, time, subprocess
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv)>1 else ".").resolve()
OUT  = Path(sys.argv[2] if len(sys.argv)>2 else "CASE_REPORT.md").resolve()

def read_json(p):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return {}

def head(path, n=20):
    try:
        return "\n".join(Path(path).read_text(errors="ignore").splitlines()[:n])
    except Exception:
        return ""

def count_lines(p):
    try:
        return sum(1 for _ in open(p,'r',encoding='utf-8',errors='ignore'))
    except Exception:
        return 0

def main():
    t0=time.time()
    manifest = ROOT/"manifest.jsonl"
    reg_idx  = ROOT/"artifact_dump/registry/_registry_index.json"
    art_idx  = ROOT/"artifact_dump/_index.json"
    report = []

    files = count_lines(manifest) if manifest.exists() else 0
    casehash = ""
    casehash_file = ROOT/"manifest.jsonl.casehash"
    if casehash_file.exists():
        casehash = casehash_file.read_text().strip()

    report.append(f"# Case Report\n")
    report.append(f"- Generated: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    report.append(f"- Root: `{ROOT}`")
    report.append(f"- Manifest lines (files): **{files}**")
    if casehash:
        report.append(f"- CaseHash (sha256 of all file sha256s): `{casehash}`")
    report.append("")

    # Artifacts summary
    arts = read_json(art_idx) if art_idx.exists() else {}
    artifacts = arts.get("artifacts", [])
    report.append("## Microsoft Artifacts")
    report.append(f"- Total harvested items: **{len(artifacts)}**")
    for sample in artifacts[:25]:
        report.append(f"  - `{sample}`")
    if len(artifacts) > 25:
        report.append(f"  - ... (+{len(artifacts)-25} more)")
    report.append("")

    # Registry summary
    reg = read_json(reg_idx) if reg_idx.exists() else {}
    processed = reg.get("processed", [])
    report.append("## Registry Hives")
    report.append(f"- Processed hives: **{len(processed)}**")
    ostf_paths = []
    for h in processed:
        tjson = ROOT / h.get("targets_path_json","")
        if tjson.exists():
            data = read_json(tjson)
            ostf = data.get("outlook_secure_temp_folder")
            if ostf:
                ostf_paths.append(ostf)
    if ostf_paths:
        report.append("### Outlook SecureTemp Folders")
        for p in sorted(set(ostf_paths)):
            report.append(f"- `{p}`")
    report.append("")

    # PST quick list
    pst_list = []
    pst_root = ROOT/"artifact_dump/pst"
    if pst_root.exists():
        for p in pst_root.rglob("*.strings.txt"):
            pst_list.append(str(p.relative_to(ROOT)))
    report.append("## PST Extracts (strings)")
    if pst_list:
        for p in pst_list[:25]:
            report.append(f"- `{p}`")
        if len(pst_list)>25:
            report.append(f"- ... (+{len(pst_list)-25} more)")
    else:
        report.append("- (none)")
    report.append("")

    # Tail samples to make it immediately useful
    if processed:
        first_txt = ROOT / processed[0].get("targets_path_txt","")
        report.append("## Sample Registry Targets (first hive)")
        report.append("```")
        report.append(head(first_txt, 80))
        report.append("```")

    OUT.write_text("\n".join(report), encoding="utf-8")
    # Optional: HTML via pandoc if available
    html = OUT.with_suffix(".html")
    try:
        subprocess.run(["pandoc", str(OUT), "-o", str(html)], check=False)
    except Exception:
        pass
    print(json.dumps({"report": str(OUT), "html": str(html), "elapsed_sec": round(time.time()-t0,2)}, indent=2))

if __name__ == "__main__":
    main()