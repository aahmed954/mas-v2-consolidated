#!/usr/bin/env bash
set -euo pipefail

echo "=== Resource Monitor ==="
echo "Timestamp: $(date)"
echo

# CPU usage
read -r cpu a b c d rest < /proc/stat
idle1=$d; total1=$((a+b+c+d))
sleep 1
read -r cpu a b c d rest < /proc/stat
idle2=$d; total2=$((a+b+c+d))
idle=$((idle2-idle1)); total=$((total2-total1))
busy=$((100*(total-idle)/ (total==0?1:total) ))
echo "CPU Usage: ${busy}%"

# GPU usage
if command -v nvidia-smi >/dev/null 2>&1; then
  gpu_util=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits | head -n1 2>/dev/null | tr -d ' ' || echo 0)
  echo "GPU Usage: ${gpu_util}%"
else
  echo "GPU Usage: N/A (nvidia-smi not found)"
fi

# Free disk space
free_gb=$(df -BG /home | awk 'NR==2{gsub("G","",$4); print $4}')
echo "Free disk: ${free_gb}GB on /home"

# Memory usage
mem_info=$(free -g | grep "^Mem:")
total_mem=$(echo "$mem_info" | awk '{print $2}')
used_mem=$(echo "$mem_info" | awk '{print $3}')
echo "Memory: ${used_mem}GB / ${total_mem}GB used"

echo
echo "=== Queue Limits ==="
echo "MAX_PARALLEL=${MAX_PARALLEL:-3}"
echo "CPU_HIGH_WATER=${CPU_HIGH_WATER:-90}%"
echo "GPU_HIGH_WATER=${GPU_HIGH_WATER:-90}%"
echo "MIN_FREE_GB=${MIN_FREE_GB:-40}GB"