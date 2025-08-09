#!/usr/bin/env python3
"""
Direct GPU ingestion for Work Buddy
Uses local BGE embeddings on your 4090
"""

import os
import sys
from pathlib import Path
from datetime import datetime
import uuid
import json

# Add MAS to path
sys.path.append("/home/starlord/mas-v2-consolidated/src")

# Force local embeddings
os.environ["EMBEDDINGS_BACKEND"] = "local"

from embeddings.client import EmbeddingClient
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Distance, VectorParams

# Setup
COLLECTION = "work-buddy-rag"
SOURCE_DIR = "/home/starlord/raycastfiles/Life"

print("🚀 Work Buddy GPU Ingestion")
print("=" * 40)
print(f"Source: {SOURCE_DIR}")
print(f"Target: {COLLECTION}")
print("Using: Local BGE on RTX 4090")
print()

# Initialize
qdrant = QdrantClient(host="localhost", port=6333)

# Local GPU embeddings
print("🔥 Initializing GPU embeddings...")
embedding_client = EmbeddingClient(
    api_key="",  # Not needed for local
    base_url="",  # Not needed for local
    model="BAAI/bge-base-en-v1.5-vllm",
    backend="local",
    l2_normalize=False,
    max_batch=32
)
print("✓ GPU embeddings ready")

# Ensure collection
try:
    info = qdrant.get_collection(COLLECTION)
    print(f"✓ Found collection with {info.points_count} existing vectors")
except:
    qdrant.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=768, distance=Distance.COSINE)
    )
    print(f"✓ Created new collection: {COLLECTION}")

# Find all files
print("\n📁 Scanning for documents...")
files = []
for ext in ["*.pdf", "*.PDF", "*.txt", "*.md", "*.csv", "*.doc", "*.docx"]:
    files.extend(Path(SOURCE_DIR).rglob(ext))

print(f"Found {len(files)} files")

# Group by category
categories = {}
for f in files:
    cat = f.parent.name
    if cat not in categories:
        categories[cat] = []
    categories[cat].append(f)

for cat, cat_files in categories.items():
    print(f"  {cat}: {len(cat_files)} files")

# Process files
print("\n🔄 Processing documents...")
total_chunks = 0
failed_files = []

for file_path in files:
    try:
        print(f"\n📄 {file_path.relative_to(SOURCE_DIR)}")
        
        # Read content (basic for now, can enhance with PyPDF2 later)
        text = ""
        try:
            # Try reading as text
            text = file_path.read_text(encoding='utf-8', errors='ignore')
        except:
            print("  ⚠ Could not read file directly")
            
            # For PDFs, we'd need PyPDF2 or pdfplumber
            # For now, mark for manual processing
            if file_path.suffix.lower() == '.pdf':
                print("  ℹ PDF needs special handling")
                # You can add PDF extraction here if needed
                
        if not text or len(text.strip()) < 50:
            print("  ⚠ Skipping - insufficient content")
            failed_files.append(str(file_path))
            continue
        
        # Smart chunking
        chunk_size = 1000
        overlap = 200
        chunks = []
        
        # Split by paragraphs first if possible
        paragraphs = text.split('\n\n')
        current_chunk = ""
        
        for para in paragraphs:
            if len(current_chunk) + len(para) < chunk_size:
                current_chunk += para + "\n\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = para + "\n\n"
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        # If no good paragraph breaks, fall back to character chunking
        if len(chunks) == 1 and len(chunks[0]) > chunk_size * 2:
            text = chunks[0]
            chunks = []
            for i in range(0, len(text), chunk_size - overlap):
                chunk = text[i:i + chunk_size]
                if chunk.strip():
                    chunks.append(chunk)
        
        print(f"  Created {len(chunks)} chunks")
        
        # Embed with GPU
        print(f"  🔥 GPU embedding...")
        embeddings = embedding_client.embed(chunks)
        
        # Prepare for Qdrant
        points = []
        for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            # Create rich metadata
            metadata = {
                "content": chunk[:500],  # First 500 chars for preview
                "full_content": chunk,
                "source": str(file_path),
                "fileName": file_path.name,
                "category": file_path.parent.name,
                "fileType": file_path.suffix,
                "chunkIndex": idx,
                "totalChunks": len(chunks),
                "charCount": len(chunk),
                "ingested": datetime.now().isoformat()
            }
            
            # Add semantic tags based on category
            if "401K" in file_path.parts:
                metadata["tags"] = ["retirement", "financial", "401k"]
            elif "Estate" in file_path.parts:
                metadata["tags"] = ["estate", "planning", "legal"]
            elif "Malpractice" in file_path.parts:
                metadata["tags"] = ["legal", "malpractice", "medical"]
            
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embedding.tolist() if hasattr(embedding, "tolist") else embedding,
                    payload=metadata
                )
            )
        
        # Store in Qdrant
        qdrant.upsert(collection_name=COLLECTION, points=points, wait=True)
        total_chunks += len(chunks)
        print(f"  ✓ Stored {len(chunks)} vectors")
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        failed_files.append(str(file_path))
        continue

# Final report
print("\n" + "=" * 40)
info = qdrant.get_collection(COLLECTION)
print(f"✅ INGESTION COMPLETE")
print(f"   Vectors in collection: {info.points_count}")
print(f"   Chunks added: {total_chunks}")
print(f"   Files processed: {len(files) - len(failed_files)}/{len(files)}")

if failed_files:
    print(f"\n⚠ Failed files ({len(failed_files)}):")
    for f in failed_files[:5]:
        print(f"   - {f}")
    if len(failed_files) > 5:
        print(f"   ... and {len(failed_files) - 5} more")

print("\n🎯 Your Life folder is now searchable in Work Buddy!")
print("   Open Raycast → RAG Talk → Ask anything about your documents")
