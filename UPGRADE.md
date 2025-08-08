- PyTorch 2.8.0 (cu128 wheels) + torchvision 0.23.0 + torchaudio 2.8.0 — keep these in lockstep.
- sentence-transformers 5.1.0, onnxruntime-gpu 1.22.0 (optional ONNX later).
- faster-whisper 1.2.0 (CTranslate2 backend) for speech.
- qdrant-client 1.15.1; recommend Qdrant server >= 1.13 for GPU HNSW indexing.

Driver shows CUDA 13.0 in `nvidia-smi` — that’s fine; cu128 wheels run on newer drivers.
