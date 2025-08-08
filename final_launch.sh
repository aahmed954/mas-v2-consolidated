#!/bin/bash

# Configuration
SSH_TARGET="starlord@192.168.68.55"
PROJECT_DIR="~/mas-v2-forensic"
NUM_WORKERS=20 # Optimized for RTX 4090 (balance GPU and CPU load)

# CRITICAL: Match Starlord's CUDA Environment (Example: CUDA 12.1)
# Check with 'nvidia-smi' on Starlord
CUDA_VERSION="cu121" 
# Check PaddlePaddle website for correct postfix (e.g., post120 for CUDA 12.x)
PADDLE_CUDA_POSTFIX="post120" 

echo "Starting Phase 1 Deployment to Starlord..."

# 1. Sync Files
echo "Syncing files..."
ssh $SSH_TARGET "mkdir -p $PROJECT_DIR/src $PROJECT_DIR/redis_data"
rsync -avz --exclude='venv/' --exclude='.git/' --exclude='__pycache__/' ./ $SSH_TARGET:$PROJECT_DIR/
if [ $? -ne 0 ]; then echo "RSYNC failed."; exit 1; fi

# 2. Setup Environment and Install Dependencies
echo "Setting up environment and installing complex dependencies..."
ssh $SSH_TARGET bash -s -- $CUDA_VERSION $PADDLE_CUDA_POSTFIX << 'EOF'
CUDA_VERSION=$1
PADDLE_CUDA_POSTFIX=$2
cd ~/mas-v2-forensic

# Install system dependencies
echo "Installing system dependencies (ffmpeg, etc.)..."
# Assuming Ubuntu/Debian on Starlord
sudo apt-get update && sudo apt-get install -y ffmpeg python3-venv libgl1-mesa-glx libsm6 libxext6

# Setup Python environment
echo "Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip wheel setuptools

# Install PyTorch (for Whisper)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/$CUDA_VERSION

# Install PaddlePaddle GPU (for PaddleOCR)
python3 -m pip install paddlepaddle-gpu==2.6.1.$PADDLE_CUDA_POSTFIX -f https://www.paddlepaddle.org.cn/whl/linux/mkl/avx/stable.html

# Install application requirements
pip install -r requirements.txt

# Verify GPU Installations
echo "Verifying GPU access..."
python3 -c "import torch; print('PyTorch CUDA Available:', torch.cuda.is_available())"
python3 -c "import paddle; paddle.utils.run_check()"
# Add validation checks here if necessary
EOF

# 3. Start Services (Redis, API, Workers) using tmux
echo "Starting Services..."
ssh $SSH_TARGET bash -s -- $NUM_WORKERS << 'EOF'
NUM_WORKERS=$1
cd ~/mas-v2-forensic
source venv/bin/activate
export PYTHONPATH=$(pwd):$PYTHONPATH

# Stop existing session and Redis
tmux kill-session -t forensic-ingestion || true
docker stop redis-ingestion || true
docker rm redis-ingestion || true

# Start Redis with Persistence (AOF)
echo "Starting Persistent Redis..."
docker run -d --name redis-ingestion --restart unless-stopped -p 6379:6379 \
    -v $(pwd)/redis_data:/data \
    redis redis-server --appendonly yes

# Start tmux session
tmux new-session -d -s forensic-ingestion

# Start the API
tmux rename-window -t forensic-ingestion:0 'api'
tmux send-keys -t forensic-ingestion:0 "uvicorn src.api_v2:app --host 0.0.0.0 --port 8000" C-m

# Start the Workers
for i in $(seq 1 $NUM_WORKERS); do
    tmux new-window -t forensic-ingestion -n "worker-$i"
    # Start RQ worker for the 'high_throughput' queue
    tmux send-keys -t forensic-ingestion:"worker-$i" "rq worker high_throughput" C-m
    sleep 0.5 # Stagger start
done

echo "DEPLOYMENT SUCCESSFUL. Services running in tmux session 'forensic-ingestion' on Starlord."
EOF
