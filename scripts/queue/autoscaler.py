#!/usr/bin/env python3
import os, time, requests, sys

PROM = os.environ.get("PROM_URL", "http://192.168.68.67:9090")
INSTANCE = os.environ.get("PROM_INSTANCE", "starlord:9100")
GPU_JOB = os.environ.get("GPU_JOB", "dcgm")
MIN_PAR = int(os.environ.get("MIN_PARALLEL", "1"))
MAX_PAR = int(os.environ.get("MAX_PARALLEL_CAP", "12"))
TARGET = float(os.environ.get("TARGET_UTIL", "0.85"))
GPU_TARGET = float(os.environ.get("GPU_TARGET_UTIL", "0.92"))
STATE_DIR = os.environ.get(
    "STATE_DIR", os.path.expanduser("~/mas-v2-consolidated/.queue_state")
)
DESIRED_FILE = os.path.join(STATE_DIR, "desired_parallel")


def prom(query: str) -> float:
    response = requests.get(
        f"{PROM}/api/v1/query", params={"query": query}, timeout=5
    )
    response.raise_for_status()
    result = response.json()["data"]["result"]
    return float(result[0]["value"][1]) if result else 0.0


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def main() -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    last_suggested = None

    cpu_query = (
        f'1 - avg(rate(node_cpu_seconds_total{{instance="{INSTANCE}",mode="idle"}}[1m]))'
    )
    gpu_query = (
        f'avg(DCGM_FI_DEV_GPU_UTIL{{instance="{INSTANCE}",job="{GPU_JOB}"}})/100'
    )

    while True:
        try:
            cpu_util = prom(cpu_query)
            gpu_util = prom(gpu_query)
            pressure = max(cpu_util / (TARGET or 1.0), gpu_util / (GPU_TARGET or 1.0), 0.25)
            suggested = int(clamp(round(MAX_PAR / max(pressure, 0.25)), MIN_PAR, MAX_PAR))
            if suggested != last_suggested:
                with open(DESIRED_FILE, "w") as f:
                    f.write(str(suggested))
                print("[autoscaler]", cpu_util, gpu_util, "->", suggested)
                last_suggested = suggested
        except Exception as e:
            print("[autoscaler] warn:", e, file=sys.stderr)
        time.sleep(15)


if __name__ == "__main__":
    main()


