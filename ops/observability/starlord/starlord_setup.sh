#!/usr/bin/env bash
set -euo pipefail
THANOS_IP="192.168.68.67"
LOG_ROOT="/home/starlord/mas-v2-consolidated/logs"

docker rm -f dcgm-exporter node-exporter cadvisor promtail >/dev/null 2>&1 || true

docker run -d --restart unless-stopped --gpus all --name dcgm-exporter -p 9400:9400 \
  nvcr.io/nvidia/k8s/dcgm-exporter:latest

docker run -d --restart unless-stopped --name node-exporter -p 9100:9100 --pid="host" \
  -v /:/host:ro,rslave prom/node-exporter:latest --path.rootfs=/host

docker run -d --restart unless-stopped --name cadvisor -p 8080:8080 \
  -v /:/rootfs:ro -v /var/run:/var/run:rw -v /sys:/sys:ro \
  -v /var/lib/docker/:/var/lib/docker:ro gcr.io/cadvisor/cadvisor:latest

cat > ~/promtail-config.yml <<YML
server: { http_listen_port: 9080, grpc_listen_port: 0 }
positions: { filename: /tmp/positions.yaml }
clients: [ { url: http://$THANOS_IP:3100/loki/api/v1/push } ]
scrape_configs:
  - job_name: masv2-logs
    static_configs:
      - targets: [localhost]
        labels: { job: masv2, host: starlord, __path__: $LOG_ROOT/*.log }
  - job_name: docker-logs
    docker_sd_configs: [ { host: unix:///var/run/docker.sock } ]
    relabel_configs:
      - { source_labels: ['__meta_docker_container_name'], target_label: 'container' }
YML
docker run -d --restart unless-stopped --name promtail \
  -v ~/promtail-config.yml:/etc/promtail/config.yml \
  -v /var/log:/var/log -v /var/run/docker.sock:/var/run/docker.sock -v $LOG_ROOT:$LOG_ROOT \
  grafana/promtail:latest -config.file=/etc/promtail/config.yml

for u in 6333 9400 9100 8080; do
  echo "Port $u -> HTTP $(curl -s -o /dev/null -w '%{http_code}' http://localhost:$u/metrics)"
done