#!/usr/bin/env python3
import os, sys, re, json, pathlib, shutil, zipfile
from pathlib import Path

ROOT=Path(sys.argv[1])
OUT =Path(sys.argv[2] if len(sys.argv)>2 else "artifact_dump")
OUT.mkdir(parents=True, exist_ok=True)

# patterns (Windows paths mirrored inside drive copy)
targets = [
 r"AppData\\Local\\Microsoft\\Office\\16\.0\\OfficeFileCache",               # Office cache
 r"AppData\\Local\\Microsoft\\Office\\UnsavedFiles",                         # Unsaved drafts
 r"AppData\\Roaming\\Microsoft\\Office\\Recent",                             # Office recents
 r"AppData\\Local\\Microsoft\\Office\\16\.0\\Wef",                           # Add-in cache
 r"AppData\\Local\\Microsoft\\Windows\\INetCache\\Content\.Outlook",         # Outlook OLK temp
 r"AppData\\Local\\Microsoft\\Outlook\\RoamCache",                           # RoamCache/Autocomplete
 r"AppData\\Local\\Microsoft\\Outlook",                                      # OST/Dat miscellany
 r"Documents\\Outlook Files",                                                # PST
 r"AppData\\Local\\Microsoft\\OneNote\\16\.0\\cache",                        # OneNote cache
 r"AppData\\Roaming\\Microsoft\\Teams",                                      # Classic Teams
 r"AppData\\Local\\Packages\\MSTeams_.*\\LocalCache\\Microsoft\\MSTeams",    # New Teams
]

def keep(p:Path):
    s=str(p).replace('/', '\\')
    return any(re.search(t, s, flags=re.IGNORECASE) for t in targets)

def write_text(path:Path, rel:Path, text:str):
    out=(OUT/rel).with_suffix((rel.suffix or "") + ".txt")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding='utf-8', errors='ignore')

def harvest():
    report=[]
    for dp,_,files in os.walk(ROOT):
        for fn in files:
            p=Path(dp)/fn
            rel=p.relative_to(ROOT)
            if keep(rel):
                # copy raw
                dst=OUT/rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(p, dst)
                except Exception:
                    pass
                # try quick text extraction for common caches
                low=fn.lower()
                if low.endswith((".lnk",".txt",".log",".json",".csv",".xml",".html",".htm",".dat",".asd",".wbk",".odl",".odlgz",".ini",".etl",".mrulist",".officeui")):
                    try:
                        data=p.read_bytes()
                        # naive text recovery
                        text=data.decode('utf-8','ignore')
                        write_text(p, rel, text)
                    except Exception:
                        pass
                report.append(str(rel))
    (OUT/"_index.json").write_text(json.dumps({"root":str(ROOT),"artifacts":report}, indent=2), encoding='utf-8')

if __name__=="__main__":
    if not ROOT.exists(): raise SystemExit("root missing")
    harvest()