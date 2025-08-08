#!/usr/bin/env python3
"""
Local embedding server that mimics the OpenAI/Together API for BGE model.
Runs on localhost:8085/embeddings
"""
import os
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Union
from sentence_transformers import SentenceTransformer
import torch
import time

app = FastAPI(title="Local Embedding Server")

# Load model on startup
model_name = os.getenv("MODEL_ID", "BAAI/bge-base-en-v1.5")
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Loading model {model_name} on {device}...")
model = SentenceTransformer(model_name)
model.to(device)
model.eval()
print(f"Model loaded successfully!")

class EmbeddingRequest(BaseModel):
    input: Union[str, List[str]]
    model: Optional[str] = model_name
    encoding_format: Optional[str] = "float"

class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: List[dict]
    model: str
    usage: dict

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model": model_name,
        "device": device,
        "max_seq_length": model.max_seq_length
    }

@app.post("/embeddings")
async def create_embeddings(request: EmbeddingRequest):
    try:
        # Convert input to list
        if isinstance(request.input, str):
            texts = [request.input]
        else:
            texts = request.input
        
        # Generate embeddings
        with torch.no_grad():
            embeddings = model.encode(texts, convert_to_tensor=False, show_progress_bar=False)
        
        # Format response
        data = []
        for i, embedding in enumerate(embeddings):
            data.append({
                "object": "embedding",
                "embedding": embedding.tolist(),
                "index": i
            })
        
        # Estimate token count (rough approximation)
        total_tokens = sum(len(text.split()) * 1.3 for text in texts)
        
        return EmbeddingResponse(
            data=data,
            model=model_name,
            usage={
                "prompt_tokens": int(total_tokens),
                "total_tokens": int(total_tokens)
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8085"))
    uvicorn.run(app, host="0.0.0.0", port=port)