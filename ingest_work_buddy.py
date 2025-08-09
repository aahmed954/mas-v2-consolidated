#!/usr/bin/env python3
"""Quick ingester using MAS v2 infrastructure"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
import uuid

# Use MAS v2 modules
sys.path.append("/home/starlord/mas-v2-consolidated/src")
from embeddings.client import EmbeddingClient
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

# Config
COLLECTION = "work-buddy-rag"
SOURCE_DIR = "/home/starlord/raycastfiles/Life"

print("🔄 Connecting to services...")
qdrant = QdrantClient(host="localhost", port=6333)

# Your existing embedding setup
embedding_client = EmbeddingClient(
    api_key=os.getenv("TOGETHER_API_KEY", ""),
    base_url=os.getenv("TOGETHER_BASE_URL", "https://api.together.xyz"),
    model="BAAI/bge-base-en-v1.5-vllm",
    backend=os.getenv("EMBEDDINGS_BACKEND", "together"),
    l2_normalize=False,
    max_batch=32
)

# Ensure collection exists
try:
    qdrant.get_collection(COLLECTION)
    print(f"✓ Using existing collection: {COLLECTION}")
except:
    from qdrant_client.models import Distance, VectorParams
    qdrant.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=768, distance=Distance.COSINE)
    )
    print(f"✓ Created collection: {COLLECTION}")

# Find all PDFs and text files
files = []
for ext in ["*.pdf", "*.PDF", "*.txt", "*.md", "*.csv"]:
    files.extend(Path(SOURCE_DIR).rglob(ext))

print(f"\n📁 Found {len(files)} files to process")

# Process files
total_chunks = 0
for file_path in files:
    try:
        print(f"\n📄 {file_path.name}...")
        
        # Read file content (using your existing loaders if available)
        text = ""
        if file_path.suffix.lower() == ".pdf":
            # Use pdfplumber or PyPDF2 if available
            try:
                import pdfplumber
                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        text += (page.extract_text() or "") + "\n"
            except:
                # Fallback to basic text extraction
                text = file_path.read_text(errors="ignore")
        else:
            text = file_path.read_text(errors="ignore")
        
        if not text or len(text) < 50:
            print("  ⚠ Skipping - no content")
            continue
        
        # Chunk the text
        chunk_size = 1000
        overlap = 200
        chunks = []
        
        for i in range(0, len(text), chunk_size - overlap):
            chunk = text[i:i + chunk_size]
            if chunk.strip():
                chunks.append(chunk)
        
        print(f"  📊 {len(chunks)} chunks")
        
        # Embed chunks
        embeddings = embedding_client.embed(chunks)
        
        # Store in Qdrant
        points = []
        for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embedding.tolist() if hasattr(embedding, "tolist") else embedding,
                    payload={
                        "content": chunk,
                        "source": str(file_path),
                        "fileName": file_path.name,
                        "category": file_path.parent.name,
                        "chunkIndex": idx,
                        "totalChunks": len(chunks),
                        "ingested": datetime.now().isoformat()
                    }
                )
            )
        
        qdrant.upsert(collection_name=COLLECTION, points=points, wait=True)
        total_chunks += len(chunks)
        print(f"  ✓ Stored {len(chunks)} vectors")
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        continue

# Final stats
info = qdrant.get_collection(COLLECTION)
print(f"\n✅ INGESTION COMPLETE")
print(f"   Total vectors in collection: {info.points_count}")
print(f"   Chunks added this run: {total_chunks}")
print(f"   Ready for Work Buddy RAG!")
