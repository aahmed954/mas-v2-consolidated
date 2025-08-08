#!/usr/bin/env python3
import os, time, requests, sys

PROM = os.environ.get("PROM_URL", "http://192.168.68.67:9090")
INSTANCE = os.environ.get("PROM_INSTANCE", "starlord:9100")   # node_exporter target label
GPU_JOB = os.environ.get("GPU_JOB", "dcgm")                   # dcgm-exporter job name
MIN_PAR = int(os.environ.get("MIN_PARALLEL", "1"))
MAX_PAR = int(os.environ.get("MAX_PARALLEL_CAP", "12"))
TARGET = float(os.environ.get("TARGET_UTIL", "0.85"))         # aim ~85% busy overall
GPU_TARGET = float(os.environ.get("GPU_TARGET_UTIL", "0.92")) # aim ~92% gpu util
STATE_DIR = os.environ.get("STATE_DIR", os.path.expanduser("~/mas-v2-consolidated/.queue_state"))
DESIRED_FILE = os.path.join(STATE_DIR, "desired_parallel")

def prom(q):
    r = requests.get(f"{PROM}/api/v1/query", params={"query": q}, timeout=5)
    r.raise_for_status()
    data = r.json()["data"]["result"]
    return float(data[0]["value"][1]) if data else None

def clamp(x, lo, hi): return max(lo, min(hi, x))

def main():
    os.makedirs(STATE_DIR, exist_ok=True)
    # PromQL: host CPU busy = 1 - avg(rate(node_cpu_seconds_total{mode="idle"}[1m]))
    # (This is the canonical way to derive CPU usage from node_exporter counters.)
    cpu_q = f'1 - avg(rate(node_cpu_seconds_total{{instance="{INSTANCE}", mode="idle"}}[1m]))'
    # GPU util via DCGM exporter (average of DCGM_FI_DEV_GPU_UTIL)
    gpu_q = f'avg(DCGM_FI_DEV_GPU_UTIL{{job="{GPU_JOB}"}})'
    
    while True:
        try:
            cpu = prom(cpu_q) or 0
            gpu = prom(gpu_q) or 0
            
            # Simple proportional control
            cpu_headroom = TARGET - cpu
            gpu_headroom = GPU_TARGET - gpu
            headroom = min(cpu_headroom, gpu_headroom)
            
            current = int(open(DESIRED_FILE).read()) if os.path.exists(DESIRED_FILE) else MIN_PAR
            
            if headroom > 0.1:  # room to grow
                desired = current + 1
            elif headroom < -0.1:  # overloaded
                desired = current - 1
            else:
                desired = current
            
            desired = clamp(desired, MIN_PAR, MAX_PAR)
            
            if desired != current:
                with open(DESIRED_FILE, 'w') as f:
                    f.write(str(desired))
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] CPU={cpu:.1%} GPU={gpu:.1%} => {current} -> {desired} parallel")
            
        except Exception as e:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Error: {e}", file=sys.stderr)
        
        time.sleep(30)

if __name__ == "__main__":
    main()