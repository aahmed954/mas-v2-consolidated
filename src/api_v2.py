# src/api_v2.py
import logging
import os
from contextlib import asynccontextmanager
from uuid import uuid4

import redis
from fastapi import FastAPI, HTTPException, Response
from prometheus_client import Counter, generate_latest
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.http.models import Distance, VectorParams
from rq import Queue
from src.config import settings
from src.embeddings.models import get_model_meta
from src.forensic_worker import process_forensic_file

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Determine embedding vector dimensions from configured model
VECTOR_DIMENSIONS = get_model_meta(settings.TOGETHER_EMBEDDING_MODEL).dim


def initialize_qdrant():
    """Ensures the Qdrant collection exists with the correct dimensions."""
    client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
    try:
        # Check if collection exists
        collection_info = client.get_collection(
            collection_name=settings.QDRANT_COLLECTION
        )
        # Verify dimensions
        if collection_info.config.params.vectors.size != VECTOR_DIMENSIONS:
            logger.error(
                f"CRITICAL: Collection exists but dimensions are incorrect ({collection_info.config.params.vectors.size} != {VECTOR_DIMENSIONS}). You must delete the collection or change the collection name and restart."
            )
            exit(1)  # Exit to prevent ingestion failure
        logger.info(f"Collection '{settings.QDRANT_COLLECTION}' verified.")
    except (UnexpectedResponse, ValueError):
        # Collection does not exist, create it
        logger.info(
            f"Creating collection '{settings.QDRANT_COLLECTION}' with {VECTOR_DIMENSIONS} dimensions (BGE-M3)."
        )
        client.create_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config=VectorParams(
                size=VECTOR_DIMENSIONS, distance=Distance.COSINE
            ),
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    initialize_qdrant()
    # (Ensure Redis connection logic is also initialized here or globally)
    yield
    # Shutdown logic (if any)


app = FastAPI(title="MAS V2 Forensic Ingestion Engine (Phase 1)", lifespan=lifespan)

# Initialize Redis and RQ
try:
    redis_conn = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT)
    redis_conn.ping()
    # 2hr timeout for large files/transcriptions/OCR
    ingestion_queue = Queue(
        "high_throughput", connection=redis_conn, default_timeout=7200
    )
    logger.info("Successfully connected to Redis.")
except redis.exceptions.ConnectionError as e:
    logger.error(f"Could not connect to Redis: {e}")
    exit(1)

# Metrics
FILES_QUEUED = Counter(
    "ingestion_files_queued_total", "Total files queued for processing"
)


class IngestRequest(BaseModel):
    remote_folder_path: str
    collection: str
    batch_id: str = None


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type="text/plain")


@app.post("/ingest_folder", status_code=202)
async def ingest_folder(request: IngestRequest):
    if not os.path.exists(request.remote_folder_path):
        raise HTTPException(status_code=400, detail="Remote path does not exist.")

    batch_id = request.batch_id or f"batch_{uuid4()}".replace("-", "_")
    total_files_queued = 0

    # Walk the directory and queue files
    # This process requires a high client-side timeout for massive drives
    for root, dirs, files in os.walk(request.remote_folder_path):
        for file in files:
            file_path = os.path.join(root, file)

            # Optional: Add filtering logic here to skip system binaries (.dll, .exe) if desired

            job = ingestion_queue.enqueue(
                process_forensic_file,
                args=(file_path, request.collection, batch_id),
                job_id=f"{batch_id}_{abs(hash(file_path))}",
            )
            total_files_queued += 1

    FILES_QUEUED.inc(total_files_queued)
    return {
        "status": "queued",
        "batch_id": batch_id,
        "total_files_queued": total_files_queued,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
    uvicorn.run(app, host="0.0.0.0", port=8002)

# ===== Work Buddy Integration Endpoint =====
@app.post("/embed")
async def create_embeddings(request: dict):
    """
    Embedding endpoint for Work Buddy RAG integration.
    Uses existing EmbeddingClient with GPU acceleration.
    """
    from src.embeddings.client import EmbeddingClient
    import os
    
    texts = request.get("texts", [request.get("text", "")])
    if isinstance(texts, str):
        texts = [texts]
    
    try:
        # Use your existing embedding infrastructure
        client = EmbeddingClient(
            api_key=os.getenv("TOGETHER_API_KEY", ""),
            base_url=os.getenv("TOGETHER_BASE_URL", "https://api.together.xyz"),
            model=request.get("model", "BAAI/bge-base-en-v1.5-vllm"),
            backend=os.getenv("EMBEDDINGS_BACKEND", "together"),
            l2_normalize=False,
            max_batch=32
        )
        
        # Get embeddings
        embeddings = []
        for text in texts:
            embedding = client.embed([text])[0]
            embeddings.append(embedding.tolist() if hasattr(embedding, "tolist") else embedding)
        
        return {
            "embeddings": embeddings,
            "model": request.get("model", "BAAI/bge-base-en-v1.5-vllm"),
            "dimensions": len(embeddings[0]) if embeddings else 768
        }
        
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})
