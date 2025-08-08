import os, subprocess, time
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import PlainTextResponse
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
CONTROL_API_KEY = os.getenv("CONTROL_API_KEY","")
REPO = os.getenv("MAS_REPO", os.path.expanduser("~/mas-v2-consolidated"))
REQS = Counter("control_requests_total","Control API requests",["path","status"])
LAT  = Histogram("control_request_seconds","Control API latency",["path"])
app = FastAPI(title="MAS Control API")
def auth(x_api_key: str | None):
    if not CONTROL_API_KEY: return True
    if not x_api_key or x_api_key != CONTROL_API_KEY: raise HTTPException(status_code=401, detail="invalid api key")
    return True
def sh(cmd:str): return subprocess.run(cmd, shell=True, capture_output=True, text=True)
@app.get("/health")
def health():
    t0=time.time(); r=sh("curl -s -o /dev/null -w '%{http_code}' http://localhost:6333/ready")
    ok=r.stdout.strip()=="200"; LAT.labels("/health").observe(time.time()-t0); REQS.labels("/health","200" if ok else "500").inc()
    return {"qdrant_ready":ok,"http":r.stdout.strip()}
@app.get("/metrics") 
def metrics(): return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
@app.post("/jobs/start")
def jobs_start(path:str, x_api_key: str | None = Header(default=None)):
    auth(x_api_key); t0=time.time()
    r=sh(f'cd {REPO} && nohup scripts/forensics/run_forensic_ingest.sh "{path}" >> logs/control-start.log 2>&1 &')
    LAT.labels("/jobs/start").observe(time.time()-t0); REQS.labels("/jobs/start","200").inc()
    return {"started":True,"path":path,"rc":r.returncode}
@app.post("/jobs/pause")
def jobs_pause(x_api_key: str | None = Header(default=None)):
    auth(x_api_key); t0=time.time(); r=sh("pkill -f run_forensic_ingest.sh || true")
    LAT.labels("/jobs/pause").observe(time.time()-t0); REQS.labels("/jobs/pause","200").inc()
    return {"paused":True}
@app.post("/qdrant/compact")
def qdrant_compact(x_api_key: str | None = Header(default=None)):
    auth(x_api_key); REQS.labels("/qdrant/compact","200").inc(); return {"ok":True}