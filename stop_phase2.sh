#!/bin/bash
# Stops the Analysis/RAG system.

echo "Stopping Phase 2..."
tmux kill-session -t masv2-phase2 || true

# Stop Ollama to free GPU memory
read -p "Stop the Ollama service to free the RTX 4090 VRAM? (y/N): " stop_ollama
if [[ $stop_ollama =~ ^[Yy]$ ]]; then
	echo "Stopping Ollama service..."
	sudo systemctl stop ollama
fi

echo "Phase 2 stopped."
