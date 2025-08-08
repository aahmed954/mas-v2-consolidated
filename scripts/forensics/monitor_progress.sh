#!/usr/bin/env bash
while true; do
    clear
    echo "=== Forensic Processing Status ==="
    echo "Time: $(date)"
    echo
    
    echo "-- Processes --"
    ps aux | grep -E "extract_ms_artifacts|registry_extract|forensic_worker" | grep -v grep | awk '{print $11,$12,$13}'
    echo
    
    echo "-- Artifacts Found --"
    if [ -f artifact_dump/_index.json ]; then
        count=$(jq '.artifacts | length' artifact_dump/_index.json 2>/dev/null || echo 0)
        echo "MS Artifacts: $count"
    fi
    find artifact_dump -type f -name "*.txt" -o -name "*.json" | wc -l | xargs -I{} echo "Total files: {}"
    echo
    
    echo "-- Registry Hives --"
    if [ -f artifact_dump/registry/_registry_index.json ]; then
        hives=$(jq '.processed | length' artifact_dump/registry/_registry_index.json 2>/dev/null || echo 0)
        echo "Processed hives: $hives"
    fi
    echo
    
    echo "-- Disk Usage --"
    du -sh artifact_dump 2>/dev/null || echo "No artifacts yet"
    echo
    
    echo "-- GPU Status --"
    nvidia-smi --query-gpu=utilization.gpu,temperature.gpu,power.draw --format=csv,noheader || echo "No GPU data"
    
    sleep 5
done