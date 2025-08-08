# MAS V2 Forensic Data Processing System

This system is designed for comprehensive forensic data processing of Windows 11 hard drives, featuring GPU-accelerated OCR, audio/video transcription, and AI-powered content enrichment.

## Architecture

- **Starlord (GPU Server)**: RTX 4090 for PaddleOCR and Whisper processing
- **Thanos (Infrastructure)**: Qdrant vector database and monitoring stack
- **Together.AI**: Cloud LLM services for content enrichment

## Components

1. **`src/config.py`**: Centralized configuration management
2. **`src/forensic_worker.py`**: Core processing worker with specialized handlers
3. **`src/api_v2.py`**: FastAPI server for job queuing
4. **`process_forensic_image.py`**: Orchestrator for targeted forensic locations
5. **`final_launch.sh`**: Deployment automation script

## Quick Start

1. **Deploy to Starlord:**
   ```bash
   chmod +x final_launch.sh
   ./final_launch.sh
   ```

2. **Start forensic processing:**
   ```bash
   python process_forensic_image.py
   ```

3. **Monitor progress:**
   ```bash
   ssh starlord@192.168.68.55
   tmux attach -t forensic-ingestion
   ```

## Prerequisites

- CUDA-capable GPU on Starlord (RTX 4090)
- Qdrant running on Thanos (192.168.68.67:6333)
- Windows 11 forensic image mounted at `/mnt/forensic_image/C/`

## Processing Strategy

The system targets high-value forensic locations:
- Office document caches and AutoRecover files
- Outlook data stores and attachment caches
- Teams application data
- OneDrive sync logs
- Browser databases and cache files
- Windows system artifacts and logs


## Operations
- **Clean & rebuild core stack**: `make clean-rebuild`
- **Start Qdrant (GPU)**: `make qdrant-up`
- **Start observability**: `make obsv-up` (Prometheus on :9091, Grafana on :3000)
- **Start Redis**: `make redis-up` (on :6380)
- **Healthcheck Together**: `SKIP_M2BERT=1 PYTHONPATH=. python scripts/embed_healthcheck.py`

## Embeddings (TogetherAI, OpenAI-compatible)
- Set `TOGETHER_API_KEY` in `.env`.
- Default model: `BAAI/bge-base-en-v1.5-vllm` (768d).
### Quick Start
```
python scripts/embed_healthcheck.py
```
### Cost
```
python scripts/cost_estimator.py BAAI/bge-large-en-v1.5 1000000
```
