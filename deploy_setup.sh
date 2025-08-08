#!/bin/bash
# ========= CONFIG (edit the first lines) =========
export ST_IP="192.168.68.55"                        # <-- Starlord LAN IP
export TOGETHER_API_KEY="tgp_v1_peF7JytuY7bC2uMRmsZxglftyn4t2Py4YYXYqDwZzMk"
export CONTROL_API_KEY="J3cSv/eWIZGNNKaTsnVOlxpYmSPboqLQ9n4LoyB7Hn0="
export COLLECTION="mas_embeddings"
export MODEL_ID="BAAI/bge-base-en-v1.5-vllm"
export QDRANT_URL="http://localhost:6333"
export SLACK_WEBHOOK=""                             # optional: Slack webhook for alerts
export HF_TOKEN=""                                  # optional: HF Pro token for TEI pulls
export MAX_PARALLEL_CAP="${MAX_PARALLEL_CAP:-12}"  # autoscaler hard ceiling
# =================================================

set -euo pipefail

echo "== System prep =="
sudo apt-get update -y
sudo apt-get install -y jq curl git python3-venv python3-pip pst-utils ffmpeg tesseract-ocr
mkdir -p ~/.venvs ~/qdrant ~/local-emb ~/mas-v2-consolidated/logs ~/.config/systemd/user

echo "== Python venv =="
python3 -m venv ~/.venvs/masv2
source ~/.venvs/masv2/bin/activate
python --version
pip -q install --upgrade pip wheel
# If your repo has requirements.txt, install it
[ -f ~/mas-v2-consolidated/requirements.txt ] && pip -q install -r ~/mas-v2-consolidated/requirements.txt || true
pip -q install requests regipy regrippy

echo "== Qdrant via Docker Compose =="
cat > ~/qdrant/docker-compose.yml <<'YAML'
version: "3.9"
services:
  qdrant:
    image: qdrant/qdrant:latest
    container_name: masv2-qdrant
    restart: unless-stopped
    ports: ["6333:6333","6334:6334"]
    volumes:
      - /home/starlord/qdrant_storage:/qdrant/storage
YAML
sudo mkdir -p /home/starlord/qdrant_storage && sudo chown -R starlord:starlord /home/starlord/qdrant_storage
cd ~/qdrant && docker compose up -d
sleep 2
curl -sf http://localhost:6333/ | jq .status

echo "== Local TEI (GPU) as fallback =="
cat > ~/local-emb/docker-compose.yml <<'YAML'
version: "3.9"
services:
  tei-bge:
    image: ghcr.io/huggingface/text-embeddings-inference:2.8.0-cuda12.1
    container_name: tei-bge
    restart: unless-stopped
    ports: ["8085:80"]
    environment:
      - MODEL_ID=BAAI/bge-base-en-v1.5
      - MAX_BATCH_SIZE=64
      - NUM_THREADS=8
      - TORCH_DTYPE=float16
      - CUDA_VISIBLE_DEVICES=0
      - HF_TOKEN=${HF_TOKEN}
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: ["gpu"]
YAML
(cd ~/local-emb && HF_TOKEN="$HF_TOKEN" docker compose up -d)
sleep 2
curl -sf http://localhost:8085/health | jq .

echo "== Promtail to ship logs to Thanos Loki =="
sudo mkdir -p /etc/promtail /var/log/mas
sudo tee /etc/promtail/config.yml >/dev/null <<'YAML'
server:
  http_listen_port: 9080
  grpc_listen_port: 0
positions:
  filename: /var/log/mas/positions.yaml
clients:
  - url: http://192.168.68.67:3100/loki/api/v1/push
scrape_configs:
  - job_name: masv2
    static_configs:
      - targets: [localhost]
        labels:
          job: masv2
          host: starlord
          __path__: /home/starlord/mas-v2-consolidated/logs/*.log
    pipeline_stages:
      - regex:
          expression: 'tokens=(?P<tokens>[0-9]+).*latency=(?P<latency>[0-9\.]+)s'
      - labels:
          tokens:
          latency:
YAML
docker rm -f promtail 2>/dev/null || true
docker run -d --name promtail --restart=unless-stopped \
  -v /etc/promtail:/etc/promtail:ro \
  -v /home/starlord/mas-v2-consolidated/logs:/home/starlord/mas-v2-consolidated/logs:ro \
  -v /var/log/mas:/var/log/mas \
  -p 9080:9080 grafana/promtail:2.9.4 \
  -config.file=/etc/promtail/config.yml

echo "== Autoscaler (Prom-driven) =="
mkdir -p ~/mas-v2-consolidated/scripts/queue ~/.queue_state
cat > ~/mas-v2-consolidated/scripts/queue/autoscaler.py <<'PY'
#!/usr/bin/env python3
import os,time,requests,sys
PROM=os.environ.get("PROM_URL","http://192.168.68.67:9090")
INSTANCE=os.environ.get("PROM_INSTANCE","starlord:9100")
GPU_JOB=os.environ.get("GPU_JOB","dcgm")
MIN_PAR=int(os.environ.get("MIN_PARALLEL","1"))
MAX_PAR=int(os.environ.get("MAX_PARALLEL_CAP","12"))
TARGET=float(os.environ.get("TARGET_UTIL","0.85"))
GPU_TARGET=float(os.environ.get("GPU_TARGET_UTIL","0.92"))
STATE_DIR=os.environ.get("STATE_DIR",os.path.expanduser("~/mas-v2-consolidated/.queue_state"))
DESIRED_FILE=os.path.join(STATE_DIR,"desired_parallel")
def prom(q):
  r=requests.get(f"{PROM}/api/v1/query",params={"query":q},timeout=5); r.raise_for_status()
  a=r.json()["data"]["result"]; return float(a[0]["value"][1]) if a else 0.0
def clamp(x,lo,hi): return max(lo,min(hi,x))
def main():
  os.makedirs(STATE_DIR,exist_ok=True); last=None
  cpu_q=f'1 - avg(rate(node_cpu_seconds_total{{instance="{INSTANCE}",mode="idle"}}[1m]))'
  gpu_q=f'avg(DCGM_FI_DEV_GPU_UTIL{{instance="{INSTANCE}",job="{GPU_JOB}"}})/100'
  while True:
    try:
      cpu=prom(cpu_q); gpu=prom(gpu_q)
      pressure=max(cpu/(TARGET or 1), gpu/(GPU_TARGET or 1), 0.25)
      suggested=int(clamp(round(MAX_PAR/max(pressure,0.25)), MIN_PAR, MAX_PAR))
      if suggested!=last:
        open(DESIRED_FILE,"w").write(str(suggested)); print("[autoscaler]",cpu,gpu,"->",suggested); last=suggested
    except Exception as e:
      print("[autoscaler] warn:",e,file=sys.stderr)
    time.sleep(15)
if __name__=="__main__": main()
PY
chmod +x ~/mas-v2-consolidated/scripts/queue/autoscaler.py

echo "== Queue supervisor (resource-aware, cgroups) =="
cat > ~/mas-v2-consolidated/scripts/queue/auto_enqueue.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="${1:-/home/starlord/mas-v2-crewai/cases_to_process}"
MAX_PARALLEL="${MAX_PARALLEL:-8}"
CPU_HIGH_WATER="${CPU_HIGH_WATER:-99}"
GPU_HIGH_WATER="${GPU_HIGH_WATER:-98}"
MIN_FREE_GB="${MIN_FREE_GB:-20}"
SCOPE_SLICE="masv2-queue.slice"
REPO="$HOME/mas-v2-consolidated"
STATE="$REPO/.queue_state"; RUNNING_DIR="$STATE/running"; DONE_DIR="$STATE/done"; FAILED_DIR="$STATE/failed"; LOG_DIR="$REPO/logs/queue"
mkdir -p "$RUNNING_DIR" "$DONE_DIR" "$FAILED_DIR" "$LOG_DIR"
cpu_usage(){ read -r _ a b c d _ < /proc/stat; idle1=$d; t1=$((a+b+c+d)); sleep 1; read -r _ a b c d _ < /proc/stat; idle2=$d; t2=$((a+b+c+d)); echo $((100*( (t2-t1)-(idle2-idle1) )/ ( (t2-t1)==0?1:(t2-t1) ) )); }
gpu_usage(){ command -v nvidia-smi >/dev/null && nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits | head -n1 | tr -d ' ' || echo 0; }
free_gb(){ df -BG /home | awk 'NR==2{gsub("G","",$4);print $4}'; }
jobs_running(){ find "$RUNNING_DIR" -type f | wc -l | tr -d ' '; }
launch_job(){ folder="$1"; name="$(basename "$folder")"; stamp="$(date +%Y%m%d-%H%M%S)"; log="$LOG_DIR/${stamp}-${name}.log"; touch "$RUNNING_DIR/$name";
  systemd-run --user --scope --slice="$SCOPE_SLICE" -p CPUQuota=100% -p MemoryMax=60G \
    bash -lc "cd '$REPO' && source ~/.venvs/masv2/bin/activate && ionice -c2 -n2 nice -n5 scripts/forensics/run_forensic_ingest.sh '$folder' >> '$log' 2>&1" >/dev/null
  echo "LAUNCHED: $name -> $log"; }
mark_done(){ mv -f "$RUNNING_DIR/$1" "$DONE_DIR/$1" 2>/dev/null || true; }
mark_failed(){ mv -f "$RUNNING_DIR/$1" "$FAILED_DIR/$1" 2>/dev/null || true; }
mapfile -t items < <(find "$BASE_DIR" -mindepth 1 -maxdepth 1 -type d -printf "%f\n" | sort); queue=()
for d in "${items[@]}"; do [[ "$d" == "Metro" ]] && queue+=("$BASE_DIR/$d"); done
for d in "${items[@]}"; do [[ "$d" == "Metro" ]] && continue; queue+=("$BASE_DIR/$d"); done
filtered=(); for f in "${queue[@]}"; do name="$(basename "$f")"; [[ -f "$DONE_DIR/$name" ]] && continue; filtered+=("$f"); done; queue=("${filtered[@]}")
echo "Queue: ${#queue[@]} folders"
declare -A attempts
while :; do
  [[ -f "$STATE/desired_parallel" ]] && dp="$(cat "$STATE/desired_parallel" 2>/dev/null || true)" && [[ "$dp" =~ ^[0-9]+$ ]] && MAX_PARALLEL="$dp"
  curr=$(jobs_running)
  if (( curr < MAX_PARALLEL && ${#queue[@]} > 0 )); then
    cpu=$(cpu_usage); gpu=$(gpu_usage); free=$(free_gb)
    if (( cpu < CPU_HIGH_WATER && gpu < GPU_HIGH_WATER && free > MIN_FREE_GB )); then folder="${queue[0]}"; queue=("${queue[@]:1}"); launch_job "$folder"; fi
  fi
  for r in "$RUNNING_DIR"/*; do [[ -f "$r" ]] || continue; name="$(basename "$r")"
    lastlog="$(ls -t "$LOG_DIR"/*-"$name".log 2>/dev/null | head -n1 || true)"
    [[ -n "$lastlog" ]] && { tail -n1 "$lastlog" | grep -qiE 'completed|ALL CHECKS PASSED' && { mark_done "$name"; echo "DONE: $name"; }; \
      grep -qiE 'Traceback|ERROR|failed' "$lastlog" && { attempts["$name"]=$(( ${attempts["$name"]:-0} + 1 )); if (( attempts["$name"] <= 2 )); then echo "RETRY: $name (${attempts["$name"]})"; launch_job "$BASE_DIR/$name"; else mark_failed "$name"; echo "FAILED: $name -> $lastlog"; fi; }; }
  done
  (( ${#queue[@]} == 0 )) && (( $(jobs_running) == 0 )) && { echo "All done."; exit 0; }
  sleep 15
done
SH
chmod +x ~/mas-v2-consolidated/scripts/queue/auto_enqueue.sh

echo "== Control API GET shim already expected on :8088 (systemd unit named mas-control). Skipping if not used. =="

echo "== systemd user services (autoscaler + queue + provider watcher) =="
tee ~/.config/systemd/user/masv2-autoscaler.service >/dev/null <<UNIT
[Unit]
Description=MAS v2 Autoscaler (Prometheus-driven)
After=network-online.target
[Service]
Type=simple
Environment=PROM_URL=http://192.168.68.67:9090
Environment=PROM_INSTANCE=starlord:9100
Environment=GPU_JOB=dcgm
Environment=MIN_PARALLEL=1
Environment=MAX_PARALLEL_CAP=${MAX_PARALLEL_CAP}
Environment=TARGET_UTIL=0.85
Environment=GPU_TARGET_UTIL=0.92
Environment=STATE_DIR=%h/mas-v2-consolidated/.queue_state
WorkingDirectory=%h/mas-v2-consolidated
ExecStart=%h/mas-v2-consolidated/scripts/queue/autoscaler.py
Restart=always
RestartSec=5
[Install]
WantedBy=default.target
UNIT

tee ~/.config/systemd/user/masv2-queue.service >/dev/null <<UNIT
[Unit]
Description=MAS v2 Forensic Ingest Queue
After=network-online.target
[Service]
Type=simple
Environment=TOGETHER_API_KEY=${TOGETHER_API_KEY}
Environment=CONTROL_API_KEY=${CONTROL_API_KEY}
Environment=QDRANT_URL=${QDRANT_URL}
Environment=COLLECTION=${COLLECTION}
Environment=MODEL_ID=${MODEL_ID}
Environment=MAX_PARALLEL=8
Environment=CPU_HIGH_WATER=99
Environment=GPU_HIGH_WATER=98
Environment=MIN_FREE_GB=20
WorkingDirectory=%h/mas-v2-consolidated
ExecStart=%h/mas-v2-consolidated/scripts/queue/auto_enqueue.sh /home/starlord/mas-v2-crewai/cases_to_process
Restart=always
RestartSec=10
[Install]
WantedBy=default.target
UNIT

mkdir -p ~/mas-v2-consolidated/scripts/watch
tee ~/mas-v2-consolidated/scripts/watch/provider_watcher.sh >/dev/null <<'SH'
#!/usr/bin/env bash
set -euo pipefail
STATE="$HOME/mas-v2-consolidated/.queue_state"
LOG="$HOME/mas-v2-consolidated/logs/provider_watcher.log"
SLACK="${SLACK_WEBHOOK:-}"
mkdir -p "$STATE" "$(dirname "$LOG")"
LAST=""
notify(){ [ -z "$SLACK" ] && return; curl -s -X POST -H 'Content-type: application/json' --data "{\"text\":\"$1\"}" "$SLACK" >/dev/null || true; }
while :; do
  cur="$(tail -n 500 "$HOME/mas-v2-consolidated/logs/embedding.log" 2>/dev/null | grep -Eo 'provider=(together|local)' | tail -n1 | sed 's/provider=//')"
  [ -z "$cur" ] && { sleep 10; continue; }
  if [ "$cur" != "$LAST" ]; then echo "$(date -Is) provider=$cur" | tee -a "$LOG"; notify ":arrows_counterclockwise: Embedding provider switched to *$cur*"; LAST="$cur"; fi
  sleep 10
done
SH
chmod +x ~/mas-v2-consolidated/scripts/watch/provider_watcher.sh

tee ~/.config/systemd/user/masv2-provider-watch.service >/dev/null <<UNIT
[Unit]
Description=MAS v2 Provider Switch Watcher
After=network-online.target
[Service]
Type=simple
Environment=SLACK_WEBHOOK=${SLACK_WEBHOOK}
ExecStart=%h/mas-v2-consolidated/scripts/watch/provider_watcher.sh
Restart=always
RestartSec=5
[Install]
WantedBy=default.target
UNIT

echo "== Enable lingering and start services =="
loginctl enable-linger "$USER" >/dev/null 2>&1 || true
systemctl --user daemon-reload
systemctl --user enable --now masv2-autoscaler.service
systemctl --user enable --now masv2-queue.service
systemctl --user enable --now masv2-provider-watch.service
systemctl --user status masv2-queue.service --no-pager | sed -n '1,12p'

echo "== Healthcheck =="
cd ~/mas-v2-consolidated
source ~/.venvs/masv2/bin/activate
PYTHONPATH=. python3 scripts/embed_healthcheck.py || PYTHONPATH=. python scripts/embed_healthcheck.py || true

echo "== Kick Metro explicitly (also runs via queue) =="
DATA="/home/starlord/mas-v2-crewai/cases_to_process/Metro"
nohup ~/mas-v2-consolidated/scripts/forensics/run_forensic_ingest.sh "$DATA" > ~/mas-v2-consolidated/logs/forensic-metro.log 2>&1 &

echo "== Tails =="
tail -n 50 ~/mas-v2-consolidated/logs/forensic-metro.log || true