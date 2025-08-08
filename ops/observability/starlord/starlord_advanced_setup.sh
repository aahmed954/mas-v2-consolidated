#!/usr/bin/env bash
set -euo pipefail

THANOS_IP="192.168.68.67"   # Observer box
LOG_ROOT="/home/starlord/mas-v2-consolidated/logs"

echo "[+] (1/6) GPU metrics: dcgm-exporter (profiling counters) on :9400"
docker rm -f dcgm-exporter >/dev/null 2>&1 || true
# Enable DCGM profiling group (adds SM/DRAM engine actives, clocks, thermals, power, etc.)
docker run -d --restart unless-stopped --gpus all --name dcgm-exporter \
  -p 9400:9400 \
  -e DCGM_EXPORTER_COLLECTORS=all \
  nvcr.io/nvidia/k8s/dcgm-exporter:latest

echo "[+] (2/6) Host metrics: node_exporter on :9100"
docker rm -f node-exporter >/dev/null 2>&1 || true
docker run -d --restart unless-stopped --name node-exporter \
  -p 9100:9100 --pid="host" \
  -v /:/host:ro,rslave prom/node-exporter:latest \
  --path.rootfs=/host

echo "[+] (3/6) Container metrics: cAdvisor on :8080"
docker rm -f cadvisor >/dev/null 2>&1 || true
docker run -d --restart unless-stopped --name cadvisor \
  -p 8080:8080 \
  -v /:/rootfs:ro -v /var/run:/var/run:rw -v /sys:/sys:ro \
  -v /var/lib/docker/:/var/lib/docker:ro \
  gcr.io/cadvisor/cadvisor:latest

echo "[+] (4/6) Promtail → Loki@$THANOS_IP:3100 (structured log parsing)"
# Promtail config with parsing of tokens= / latency= to unlock nicer Loki queries
cat > ~/promtail-config.yml <<YML
server: { http_listen_port: 9080, grpc_listen_port: 0 }
positions: { filename: /tmp/positions.yaml }
clients: [ { url: http://$THANOS_IP:3100/loki/api/v1/push } ]
scrape_configs:
  - job_name: masv2-logs
    static_configs:
      - targets: [localhost]
        labels: { job: masv2, host: starlord, __path__: $LOG_ROOT/*.log }
    pipeline_stages:
      - regex:
          expression: "tokens=(?P<tokens>[0-9]+)"
      - regex:
          expression: "latency=(?P<latency>[0-9]+)"
      - labels:
          tokens:
          latency:
  - job_name: docker-logs
    docker_sd_configs: [ { host: unix:///var/run/docker.sock } ]
    relabel_configs:
      - { source_labels: ['__meta_docker_container_name'], target_label: 'container' }
YML
docker rm -f promtail >/dev/null 2>&1 || true
docker run -d --restart unless-stopped --name promtail \
  -v ~/promtail-config.yml:/etc/promtail/config.yml \
  -v /var/log:/var/log \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v $LOG_ROOT:$LOG_ROOT \
  grafana/promtail:latest -config.file=/etc/promtail/config.yml

echo "[+] (5/6) OpenTelemetry for Python ingestion → Tempo@$THANOS_IP:4317"
# Instrument your Python (requests/httpx, FastAPI) and export OTLP to Tempo (gRPC)
source ~/.venvs/masv2/bin/activate || true
pip install -U opentelemetry-distro opentelemetry-exporter-otlp \
  opentelemetry-instrumentation-requests opentelemetry-instrumentation-urllib3 \
  opentelemetry-instrumentation-logging opentelemetry-instrumentation-fastapi || true

# Global env used by your runners
cat > ~/.otel-env-mas <<'ENV'
export OTEL_SERVICE_NAME=masv2-ingest
export OTEL_RESOURCE_ATTRIBUTES=deployment.environment=prod,host.role=starlord
export OTEL_EXPORTER_OTLP_PROTOCOL=grpc
export OTEL_EXPORTER_OTLP_ENDPOINT=grpc://192.168.68.67:4317
export OTEL_PYTHON_LOG_CORRELATION=true
ENV
grep -q OTEL_SERVICE_NAME ~/.bashrc || echo '. ~/.otel-env-mas' >> ~/.bashrc
. ~/.otel-env-mas

# Wrapper so any python entrypoint is auto-instrumented *without* code edits:
mkdir -p scripts
cat > scripts/py_otel <<'BASH'
#!/usr/bin/env bash
set -euo pipefail
. ~/.otel-env-mas 2>/dev/null || true
exec opentelemetry-instrument python "$@"
BASH
chmod +x scripts/py_otel

echo "[+] (6/6) Sanity probes"
for u in 6333 9400 9100 8080; do
  echo "  - http://localhost:$u/metrics -> HTTP $(curl -s -o /dev/null -w '%{http_code}' http://localhost:$u/metrics)"
done
echo "Done. Exporters, Promtail, and OTEL are set."