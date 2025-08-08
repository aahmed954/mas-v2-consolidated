#!/bin/bash

# Configuration
SSH_TARGET="starlord@192.168.68.55"
SSH_THANOS="thanos@192.168.68.67" # Needed only for cleanup
PROJECT_DIR="$HOME/mas-v2-consolidated"
NUM_WORKERS=24 # Optimized for RTX 4090 (balance GPU and CPU load)

# CRITICAL: Match Starlord's CUDA Environment (Check with 'nvidia-smi')
CUDA_VERSION="cu121"
PADDLE_CUDA_POSTFIX="post120"

echo "Starting Consolidated Deployment to Starlord ($SSH_TARGET)..."

# ------------------------------------------------------------------------------
# STEP 0: CLEANUP (Decommission previous setups)
# ------------------------------------------------------------------------------
echo "--- 0. Cleaning up previous deployments ---"

# Cleanup Thanos (if accessible)
echo "Attempting cleanup of Thanos (192.168.68.67)..."
# Use a timeout in case Thanos is offline
ssh -o ConnectTimeout=10 $SSH_THANOS bash <<'EOF'
if [ -d "~/monitoring" ]; then
    cd ~/monitoring && docker-compose down || true
fi
docker stop qdrant-forensic node_exporter redis-exporter || true
docker rm qdrant-forensic node_exporter redis-exporter || true
echo "Thanos cleanup complete."
EOF

# Cleanup Starlord
echo "Cleaning up Starlord (192.168.68.55)..."
ssh $SSH_TARGET bash <<'EOF'
echo "Stopping previous application sessions (tmux)..."
tmux kill-session -t forensic-ingestion || true
tmux kill-session -t masv2-system || true
tmux kill-session -t masv2-phase2 || true

echo "Stopping and removing previous Docker containers..."
# Stop containers from previous consolidated attempt
docker compose -f ~/mas-v2-consolidated/docker-compose.infra.yml down || true

# Stop containers from previous distributed attempt
docker stop redis-ingestion || true
docker rm redis-ingestion || true

echo "Starlord cleanup complete."
EOF

# ------------------------------------------------------------------------------
# STEP 1: SYNC FILES
# ------------------------------------------------------------------------------
echo "--- 1. Syncing files ---"

# Ensure all necessary data directories exist on Starlord
ssh $SSH_TARGET "mkdir -p ~/mas-v2-consolidated/src ~/mas-v2-consolidated/config ~/mas-v2-consolidated/data/qdrant_storage ~/mas-v2-consolidated/data/redis_data ~/mas-v2-consolidated/data/batch_processing"

rsync -avz --exclude='venv/' --exclude='.git/' --exclude='data/' \
	./ $SSH_TARGET:~/mas-v2-consolidated/

if [ $? -ne 0 ]; then
	echo "RSYNC failed."
	exit 1
fi

# ------------------------------------------------------------------------------
# STEP 2: SETUP ENVIRONMENT AND DEPENDENCIES
# ------------------------------------------------------------------------------
echo "--- 2. Setting up Python environment and installing GPU dependencies ---"
ssh $SSH_TARGET bash -s -- $CUDA_VERSION $PADDLE_CUDA_POSTFIX <<'EOF'
CUDA_VERSION=$1
PADDLE_CUDA_POSTFIX=$2

cd ~/mas-v2-consolidated

# Install system dependencies
echo "Installing system dependencies (ffmpeg, docker-compose, etc.)..."
# Assuming Ubuntu/Debian on Starlord
sudo apt-get update && sudo apt-get install -y ffmpeg python3-venv libsm6 libxext6

# Setup Python environment
echo "Setting up Python environment..."
if [ ! -d "venv" ]; then python3 -m venv venv; fi
source venv/bin/activate
pip install --upgrade pip wheel setuptools

# Install PyTorch (for Whisper) - Utilizes RTX 4090
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/$CUDA_VERSION

# Install PaddlePaddle GPU (for PaddleOCR) - Utilizes RTX 4090
python3 -m pip install paddlepaddle-gpu==2.6.1.$PADDLE_CUDA_POSTFIX -f https://www.paddlepaddle.org.cn/whl/linux/mkl/avx/stable.html

# Install application requirements
pip install -r requirements.txt

# Verify GPU Installations
echo "Verifying GPU access..."
python3 -c "import torch; print('PyTorch CUDA Available:', torch.cuda.is_available())"
python3 -c "import paddle; paddle.utils.run_check()"
EOF

# ------------------------------------------------------------------------------
# STEP 3: LAUNCH INFRASTRUCTURE AND APPLICATION
# ------------------------------------------------------------------------------
echo "--- 3. Launching Infrastructure and Application (Phase 1) ---"
ssh $SSH_TARGET bash -s -- $NUM_WORKERS <<'EOF'
NUM_WORKERS=$1

cd ~/mas-v2-consolidated
source venv/bin/activate
export PYTHONPATH=$(pwd):$PYTHONPATH

# Start Infrastructure (Qdrant, Redis, Monitoring)
echo "Starting Infrastructure (Docker Compose)..."
docker compose -f docker-compose.infra.yml up -d
sleep 15 # Wait for infrastructure to stabilize

# Start Application (Pipelines A and B)
echo "Starting Application (tmux)..."
tmux new-session -d -s masv2-system

# Start the API (Pipeline A)
tmux rename-window -t masv2-system:0 'api-ingest'
# Ensure src/api_v2.py exists and is configured correctly
tmux send-keys -t masv2-system:0 "uvicorn src.api_v2:app --host 0.0.0.0 --port 8000" C-m

# Start the Enrichment Manager (Pipeline B)
tmux new-window -t masv2-system -n 'enrichment-mgr'
tmux send-keys -t masv2-system:enrichment-mgr "python3 src/enrichment_manager.py" C-m

# Start the Workers (Pipeline A)
for i in $(seq 1 $NUM_WORKERS); do
    tmux new-window -t masv2-system -n "worker-$i"
    tmux send-keys -t masv2-system:"worker-$i" "rq worker high_throughput" C-m
    sleep 0.5
done

echo "-----------------------------------------------------------------"
echo "CONSOLIDATED DEPLOYMENT SUCCESSFUL ON STARLORD."
echo "Pipelines A (Ingestion) and B (Enrichment) are running in tmux session 'masv2-system'."
echo "Grafana: http://192.168.68.55:3000 | API: http://192.168.68.55:8000"
echo "-----------------------------------------------------------------"
EOF
