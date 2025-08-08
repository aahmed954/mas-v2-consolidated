#!/usr/bin/env python3
import os, sys, json, hashlib, time, subprocess, base64
from pathlib import Path

ROOT = Path(sys.argv[1])
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("manifest.jsonl")
def sha256(p, buf=1024*1024):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        while True:
            b=f.read(buf)
            if not b: break
            h.update(b)
    return h.hexdigest()

def main():
    t0=time.time()
    n=0
    with open(OUT, 'w', encoding='utf-8') as w:
        for dp,_,files in os.walk(ROOT):
            for fn in files:
                p=Path(dp)/fn
                try:
                    st=p.stat()
                    h=sha256(p)
                    rec={"path":str(p), "size":st.st_size, "mtime":int(st.st_mtime), "sha256":h}
                    w.write(json.dumps(rec, ensure_ascii=False)+"\n")
                    n+=1
                except Exception as e:
                    w.write(json.dumps({"path":str(p),"error":str(e)})+"\n")
    sig=None
    try:
        # optional: sign manifest with host key if available
        res=subprocess.run(["ssh-keygen","-Y","sign","-n","file","-f",str(Path.home()/".ssh/id_ed25519"),str(OUT)],
                           capture_output=True,text=True)
        sig=res.stderr if res.returncode==0 else None
    except Exception:
        pass
    print(json.dumps({"root":str(ROOT),"files":n,"elapsed_sec":round(time.time()-t0,2),"signed": bool(sig)},indent=2))
if __name__=="__main__":
    if not ROOT.exists(): sys.exit("Root not found")
    main()