#!/usr/bin/env bash
set -euo pipefail

echo "== Stop/disable known systemd services (ignore if absent) =="
for svc in qdrant redis-server redis prometheus grafana; do
  sudo systemctl stop "$svc" 2>/dev/null || true
  sudo systemctl disable "$svc" 2>/dev/null || true
done

echo "== Stop/remove ALL docker containers =="
docker ps -aq | xargs -r docker stop
docker ps -aq | xargs -r docker rm -f

echo "== Prune dangling images/volumes/builders =="
docker image prune -af || true
docker volume prune -f || true
docker network prune -f || true
docker builder prune -af || true

echo "== Kill any processes on common ports =="
for p in 6333 6334 6379 6380 3000 9090 9091; do
  sudo lsof -t -i :$p -sTCP:LISTEN | xargs -r sudo kill -9
done

echo "== Backup & remove known data dirs if present =="
TS=$(date +%Y%m%d-%H%M%S)
for d in "$HOME/qdrant_storage" "./qdrant_storage" "./redis_data" "./grafana_storage"; do
  if [ -d "$d" ]; then
    tar -C "$(dirname "$d")" -czf "$HOME/cleanup-backup-$TS-$(basename "$d").tgz" "$(basename "$d")" || true
    rm -rf "$d"
    echo "Backed up and removed $d"
  fi
done

echo "== Recreate Qdrant storage dir =="
mkdir -p ./qdrant_storage

echo "== Bring up GPU Qdrant on 6333/6334 =="
# Ensure NVIDIA runtime is wired
if ! docker info 2>/dev/null | grep -qi 'Runtimes:.*nvidia'; then
  echo "NVIDIA container runtime not detected. Running setup..."
  sudo apt update && sudo apt install -y nvidia-container-toolkit
  sudo nvidia-ctk runtime configure --runtime=docker
  sudo systemctl restart docker
fi

docker compose -f docker-compose.gpu.yml up -d

echo "== Qdrant health =="
sleep 2
curl -s http://localhost:6333/ready || true
echo; echo "Done."