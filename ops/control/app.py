import os, subprocess, time, json, shlex
import requests
from fastapi import FastAPI, HTTPException, Header, Query
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
    t0=time.time(); r=sh("curl -s -o /dev/null -w '%{http_code}' http://localhost:6333/")
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

@app.post("/system-check")
def system_check(
    x_api_key: str | None = Header(default=None),
    qdrant_url: str | None = None,
    collection: str | None = None,
    model_id: str | None = None,
    dim_expected: int | None = None,
    distance_expected: str | None = None,
):
    auth(x_api_key)
    env = os.environ.copy()
    if qdrant_url:        env["QDRANT_URL"] = qdrant_url
    if collection:        env["COLLECTION"] = collection
    if model_id:          env["MODEL_ID"] = model_id
    if dim_expected:      env["DIM_EXPECTED"] = str(dim_expected)
    if distance_expected: env["DISTANCE_EXPECTED"] = distance_expected
    
    try:
        r = subprocess.run(
            [f"{REPO}/scripts/checks/full_system_check.sh"],
            capture_output=True, text=True, env=env, timeout=180
        )
        return {"ok": r.returncode == 0, "returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr}
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=504, detail="system check timed out")

@app.get("/system-check/run")
def system_check_run(
    key: str = Query(..., alias="key"),
    qdrant_url: str | None = Query(None),
    collection: str | None = Query(None),
    model_id: str | None = Query(None),
    dim_expected: int | None = Query(None),
    distance_expected: str | None = Query(None),
):
    # GET shim so Grafana can trigger without POST headers
    if key != os.environ.get("CONTROL_API_KEY"):
        raise HTTPException(status_code=401, detail="unauthorized")
    payload = {}
    if qdrant_url:        payload["qdrant_url"] = qdrant_url
    if collection:        payload["collection"] = collection
    if model_id:          payload["model_id"] = model_id
    if dim_expected:      payload["dim_expected"] = dim_expected
    if distance_expected: payload["distance_expected"] = distance_expected
    r = requests.post("http://127.0.0.1:8088/system-check", json=payload, timeout=180, headers={"x-api-key": key})
    try:
        data = r.json()
    except Exception:
        raise HTTPException(status_code=502, detail=f"bad response from system-check: {r.status_code}")
    return {
        "ok": data.get("ok", False),
        "returncode": data.get("returncode"),
        "api": data.get("api","auto"),
        "stdout_tail": data.get("stdout","")[-4000:],
        "stderr_tail": data.get("stderr","")[-2000:]
    }