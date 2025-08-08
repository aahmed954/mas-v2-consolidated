# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a forensic data processing system designed for analyzing Windows 11 hard drives. It features GPU-accelerated processing (OCR, audio/video transcription), AI-powered content enrichment, and distributed processing with failover capabilities.

## Commands

### Environment Setup
```bash
# Create and activate virtual environment
python3 -m venv ~/.venvs/masv2
source ~/.venvs/masv2/bin/activate

# Install dependencies
pip install -r requirements.txt

# Setup environment variables
cp .env.example .env
# Edit .env with your API keys

# Clean and rebuild infrastructure
./scripts/clean_rebuild.sh
```

### Running the System
```bash
# Deploy to Starlord (GPU server)
./final_launch.sh

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

# Stop services
make qdrant-down
make redis-down
make obsv-down

# Clean rebuild
make clean-rebuild
make ports-guard     # Fix port conflicts
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

### Testing
```bash
# Full system check
./scripts/checks/full_system_check.sh

# Environment validation
./scripts/check_env.sh

# Embeddings health check
python scripts/embed_healthcheck.py

# Test failover
python test_failover_simple.py
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
     - Audio/Video: Whisper transcription
     - Databases: SQLite extraction

3. **Embeddings** (`src/embeddings/`)
   - Failover system: TogetherAI → Local fallback
   - Circuit breaker pattern for resilience
   - Supports BGE, GTE-modernbert models
   - Adaptive batching and L2 normalization

4. **Enrichment** (`src/enrichment_manager.py`)
   - Batch processing pipeline
   - Queries Qdrant for pending records
   - Adds AI-generated forensic summaries

5. **Queue Automation** (`scripts/queue/`)
   - **auto_enqueue.sh**: Resource-aware job scheduler with cgroups
   - **autoscaler.py**: Prometheus-driven parallel job scaling
   - Monitors CPU/GPU utilization and adjusts concurrency
   - Automatic retries and failure handling

### Infrastructure

- **Starlord (192.168.68.55)**: GPU server with RTX 4090
- **Thanos (192.168.68.67)**: Qdrant vector DB and monitoring
- **Redis**: Job queue with persistence (port 6380)
- **Qdrant**: Vector storage (port 6333)
- **TEI (Text Embeddings Inference)**: Local fallback on port 8085
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

### Processing Targets

The system targets high-value forensic locations:
- Office document caches and AutoRecover
- Outlook data stores and attachments
- Teams application data
- OneDrive sync logs
- Browser databases and caches
- Windows system artifacts

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