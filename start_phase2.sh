#!/bin/bash
# Starts the Analysis/RAG system.

PROJECT_DIR="$HOME/mas-v2-consolidated"
API_PORT=8001

# 1. Stop Phase 1 (if running)
echo "Stopping Phase 1 (Ingestion/Enrichment)..."
tmux kill-session -t masv2-system || true

# 2. Start Ollama (if not already running) - Loads model onto RTX 4090
if ! systemctl is-active --quiet ollama; then
	echo "Starting Ollama service..."
	sudo systemctl start ollama
	# Ensure models are pulled (e.g., ollama pull llama3:70b)
	echo "Waiting for model load..."
	sleep 60 # Allow time for large model load onto GPU
fi

# 3. Start the Analysis API (Requires src/api_analysis.py to be developed)
echo "Starting Phase 2 API..."
cd $PROJECT_DIR
source venv/bin/activate
export PYTHONPATH=$(pwd):$PYTHONPATH

tmux new-session -d -s masv2-phase2
# Replace 'src.api_analysis:app' with your actual CrewAI API entrypoint
tmux send-keys -t masv2-phase2:0 "uvicorn src.api_analysis:app --host 0.0.0.0 --port $API_PORT" C-m

echo "Phase 2 Analysis API started on port $API_PORT."
