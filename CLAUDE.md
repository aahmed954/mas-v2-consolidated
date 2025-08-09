# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a forensic data processing system designed for analyzing Windows 11 hard drives. It features GPU-accelerated processing (OCR, audio/video transcription), AI-powered content enrichment, and distributed processing with failover capabilities.

## Commands

### Environment Setup
```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Setup environment variables
cp .env.example .env
# Edit .env with your API keys:
# - TOGETHER_API_KEY (required for embeddings)
# - TOGETHER_EMBEDDING_MODEL (default: BAAI/bge-base-en-v1.5-vllm)
# - EMBEDDINGS_BACKEND (together/local)

# Load environment variables
source scripts/load_env.sh

# Clean and rebuild infrastructure
./scripts/clean_rebuild.sh
```

### Running the System
```bash
# Deploy to Starlord (GPU server)
./final_launch.sh

# Start API server
make api

# Start workers (4 concurrent)
make workers

# Run forensic ingest with logging
make metro

# Start forensic processing
python process_forensic_image.py

# Monitor processing
./scripts/forensics/monitor_progress.sh

# Check resource usage
./scripts/queue/monitor_resources.sh
```

### Infrastructure Management
```bash
# Start services
make qdrant-up       # GPU-enabled Qdrant
make qdrant-cpu      # CPU-only Qdrant
make redis-up        # Redis queue
make obsv-up         # Monitoring stack
make tei             # Text Embeddings Inference

# Stop services
make qdrant-down
make redis-down
make obsv-down

# Clean rebuild
make clean-rebuild
make ports-guard     # Fix port conflicts

# Check service status
make status
make health          # Comprehensive health check
```

### Automated Queue Management
```bash
# Check systemd services status
systemctl --user status masv2-queue
systemctl --user status masv2-autoscaler
systemctl --user status masv2-provider-watch

# Restart services if needed
systemctl --user restart masv2-queue
systemctl --user restart masv2-autoscaler

# View logs
journalctl --user -u masv2-queue -f
journalctl --user -u masv2-autoscaler -f

# Manual queue control
scripts/queue/auto_enqueue.sh /home/starlord/mas-v2-crewai/cases_to_process
```

### Forensic Processing Pipeline
```bash
# Full forensic ingest
scripts/forensics/run_forensic_ingest.sh /path/to/folder

# Individual steps:
# 1. Create manifest
python scripts/forensics/hash_and_manifest.py /path manifest.jsonl

# 2. Sign manifest (SSH/GPG)
scripts/forensics/sign_manifest.sh manifest.jsonl

# 3. Extract MS artifacts
python scripts/forensics/extract_ms_artifacts.py /path artifact_dump

# 4. Extract registry
python scripts/forensics/registry_extract.py /path artifact_dump/registry

# 5. Generate report
python scripts/forensics/generate_report.py artifact_dump forensic_report.html
```

### Testing
```bash
# Full system check
./scripts/checks/full_system_check.sh

# Environment validation
./scripts/check_env.sh

# Embeddings health check
python scripts/embed_healthcheck.py
make health

# Test failover
python test_failover_simple.py

# API metrics check
curl -s http://localhost:8000/metrics

# Control API system check
curl -s "http://localhost:8088/system-check/run?key=$CONTROL_API_KEY" | jq .
```

## Architecture

### Core Components

1. **API Server** (`src/api_v2.py`)
   - FastAPI on port 8000
   - Receives folder ingestion requests
   - Creates RQ jobs for processing
   - Prometheus metrics at `/metrics`

2. **Worker System** (`src/forensic_worker.py`)
   - Processes files from Redis queue
   - Specialized handlers for different file types:
     - Documents/Images: PaddleOCR via Unstructured
     - Audio/Video: Whisper transcription (base model)
     - Databases: SQLite extraction

3. **Embeddings** (`src/embeddings/`)
   - Failover system: TogetherAI → Local TEI fallback
   - Circuit breaker pattern for resilience
   - Supports BGE, GTE-modernbert models
   - Adaptive batching (max 32) and optional L2 normalization

4. **Enrichment** (`src/enrichment_manager.py`)
   - Batch processing pipeline
   - Queries Qdrant for pending records
   - Adds AI-generated forensic summaries (meta-llama-3-70b-instruct)

5. **Queue Automation** (`scripts/queue/`)
   - **auto_enqueue.sh**: Resource-aware job scheduler with cgroups
   - **autoscaler.py**: Prometheus-driven parallel job scaling
   - Monitors CPU (85%) and GPU (92%) utilization thresholds
   - Max parallel cap: 12 jobs
   - State directory: `~/.queue_state`

### Infrastructure

- **Starlord (192.168.68.55)**: GPU server with RTX 4090
- **Thanos (192.168.68.67)**: Qdrant vector DB and monitoring
- **Redis**: Job queue with persistence (port 6379/6380)
- **Qdrant**: Vector storage (port 6333, collection: mas_embeddings)
- **TEI**: Local embeddings fallback on port 8085
- **Promtail**: Log shipping to Thanos Loki
- **Control API**: Management endpoint on port 8088

### Key Design Patterns

1. **Graceful Degradation**: Optional dependencies handled gracefully
   ```python
   try:
       import specialized_module
       MODULE_AVAILABLE = True
   except ImportError:
       MODULE_AVAILABLE = False
   ```

2. **Thread Safety**: Use locks for shared state
   ```python
   with self.stats_lock:
       self.stats['processed'] += 1
   ```

3. **Chunking**: Large files processed in chunks (100MB default)

4. **Failover**: Automatic switching between embedding providers

5. **OCR Strategy**: Uses hi_res strategy for maximum extraction

### Processing Targets

The system targets high-value forensic locations:
- Office document caches and AutoRecover
- Outlook data stores and attachments
- Teams application data
- OneDrive sync logs
- Browser databases and caches
- Windows system artifacts

### Dependencies

Key versions (from requirements.txt):
- PyTorch 2.8.0 with CUDA 12.8
- sentence-transformers 5.1.0
- faster-whisper 1.2.0
- qdrant-client 1.15.1 (requires Qdrant server >= 1.13)
- PaddlePaddle for GPU-accelerated OCR

## Important Notes

- Windows 11 forensic image expected at `/mnt/forensic_image/C/`
- GPU acceleration requires CUDA-capable GPU
- Always ensure Redis and Qdrant are running before processing
- Use tmux sessions for long-running processes
- Monitor Grafana dashboards at http://localhost:3000
- Systemd user services manage queue automation (enable lingering with `loginctl enable-linger`)
- Autoscaler adjusts parallelism based on CPU/GPU metrics from Prometheus
- Queue processes cases from `/home/starlord/mas-v2-crewai/cases_to_process/`
- Resource limits: CPU quota 100%, Memory max 60GB per job
- Provider switching monitored and logged to Slack if webhook configured
- Current development branch: staging/forensics-stable
- Main branch for PRs: main