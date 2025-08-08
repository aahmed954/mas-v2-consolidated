import logging
import os
from uuid import uuid4

import pandas as pd
import redis
import sqlalchemy
import torch
import whisper
from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct
from rq import Worker
from src.embeddings.client import EmbeddingClient
from src.embeddings.models import get_model_meta
from src.config import settings
from tenacity import retry, stop_after_attempt, wait_exponential
from unstructured.chunking.title import chunk_by_title
from unstructured.partition.auto import partition

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Initialization (Worker Setup) ---

# Initialize Qdrant Client
qdrant_client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)

# Embedding client (Together/OpenAI-compatible)
embed_client = EmbeddingClient(
    api_key=settings.TOGETHER_API_KEY,
    base_url=settings.TOGETHER_BASE_URL,
    model=settings.TOGETHER_EMBEDDING_MODEL,
    backend=settings.EMBEDDINGS_BACKEND,
    l2_normalize=settings.EMBEDDINGS_L2_NORMALIZE,
    max_batch=settings.EMBEDDINGS_MAX_BATCH,
)

def ensure_qdrant_collection(collection_name: str, dim: int):
    from qdrant_client.http.models import Distance, VectorParams
    try:
        info = qdrant_client.get_collection(collection_name)
        existing_dim = info.config.params.vectors.size  # type: ignore
        if existing_dim != dim:
            raise RuntimeError(
                f"Qdrant collection '{collection_name}' has dim={existing_dim}, "
                f"but embedding model requires dim={dim}. Create a new collection or re-embed."
            )
    except Exception:
        qdrant_client.recreate_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        logger.info(f"Created Qdrant collection '{collection_name}' with size={dim} (COSINE).")


# Initialize Whisper Model (Local GPU)
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
try:
    # Temperature 0 for deterministic, forensic accuracy
    whisper_model = whisper.load_model(settings.WHISPER_MODEL_SIZE, device=DEVICE)
    logger.info(f"Whisper model '{settings.WHISPER_MODEL_SIZE}' loaded onto {DEVICE}.")
except Exception as e:
    whisper_model = None
    logger.warning(f"Failed to load Whisper model. Transcription disabled.")

# --- Helper Functions ---


# Resilient embedding generation with exponential backoff
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    reraise=True,
)
def generate_embeddings(texts: list[str]):
    """Generate embeddings using the batch embedding service"""
    return embedding_service.embed_documents(texts, use_batch=len(texts) > 10)


# --- Processing Strategies ---


def process_standard(file_path):
    """Handles documents, images, emails using Unstructured/PaddleOCR."""
    logger.info(
        f"Using Unstructured (Strategy: {settings.OCR_STRATEGY}) for {file_path}"
    )
    # Unstructured will automatically leverage PaddleOCR if installed and strategy is hi_res
    elements = partition(
        filename=file_path,
        strategy=settings.OCR_STRATEGY,
        pdf_infer_table_structure=True,
    )
    return elements


def process_media(file_path):
    """Handles audio/video transcription using Whisper."""
    if not whisper_model:
        return None
    logger.info(f"Transcribing media file: {file_path}")
    try:
        result = whisper_model.transcribe(file_path, verbose=False, temperature=0)
        from unstructured.documents.elements import Text

        return [Text(result["text"])]
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return None


def process_database(file_path, collection, batch_id):
    """Handles SQLite databases (Browser history, caches)."""
    logger.info(f"Processing database file: {file_path}")
    try:
        engine = sqlalchemy.create_engine(f"sqlite:///{file_path}")
        inspector = sqlalchemy.inspect(engine)
        table_names = inspector.get_table_names()
        total_rows = 0

        with engine.connect() as connection:
            for table in table_names:
                try:
                    df = pd.read_sql_table(table, connection)
                    texts = []
                    for index, row in df.iterrows():
                        # Create structured text representation of the row
                        row_text = f"DB: {os.path.basename(file_path)} | Table: {table} | Row: {index}\n"
                        row_text += "\n".join(
                            [f"  {col}: {str(val)}" for col, val in row.items()]
                        )
                        texts.append(row_text)

                    if texts:
                        # Upload database rows directly (Bypass standard chunking/enrichment)
                        upload_to_qdrant(
                            texts,
                            f"{file_path}#table={table}",
                            collection,
                            batch_id,
                        )
                        total_rows += len(texts)
                except Exception as e:
                    logger.error(f"Error processing table {table}: {e}")
        return {"status": "completed", "extracted_chunks": total_rows}
    except Exception as e:
        logger.error(f"Database processing failed: {e}")
        return {"status": "failed", "error": str(e)}


# --- Upload Function (Updated for Pipeline A) ---


def upload_to_qdrant(texts, source_path, collection, batch_id):
    ensure_qdrant_collection(collection, get_model_meta(settings.TOGETHER_EMBEDDING_MODEL).dim)
    # Note: 'enrichment' parameter is removed
    vectors, _ = embed_client.embed_texts(texts)
    points = []
    for i, text in enumerate(texts):
        payload = {
            "source_path": source_path,
            "text": text,
            "batch_id": batch_id,
            "file_type": os.path.splitext(source_path)[1].lower(),
            # Set summary to PENDING. Pipeline B will update it.
            "forensic_summary": "PENDING",
        }
        # CRITICAL: We use UUID4 here. Pipeline B uses this ID as custom_id.
        points.append(PointStruct(id=str(uuid4()), vector=vectors[i], payload=payload))

    if points:
        # Ensure collection exists with BGE-M3 dimensions (1024)
        try:
            qdrant_client.get_collection(collection)
        except:
            # Create collection if it doesn't exist
            from qdrant_client.http.models import Distance, VectorParams

            qdrant_client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(
                    size=get_model_meta(settings.TOGETHER_EMBEDDING_MODEL).dim, distance=Distance.COSINE  # BGE-M3 embedding size
                ),
            )
            logger.info(
                f"Created Qdrant collection: {collection} with BGE-M3 dimensions (1024)"
            )

        qdrant_client.upsert(collection_name=collection, wait=True, points=points)
        logger.info(f"Uploaded {len(points)} points to Qdrant collection: {collection}")


# --- Main Worker Function (Executed by RQ) ---


def process_forensic_file(file_path: str, collection: str, batch_id: str):
    logger.info(f"Starting processing: {file_path}")
    try:
        ext = os.path.splitext(file_path)[1].lower()
        # Define comprehensive extensions for triage
        DB_EXTS = [
            ".db",
            ".sqlite",
            ".sqlite3",
            ".edb",
        ]  # Added EDB for Windows Search Index
        MEDIA_EXTS = [".mp3", ".wav", ".m4a", ".mp4", ".mov", ".avi", ".wmv", ".wma"]

        if ext in DB_EXTS:
            return process_database(file_path, collection, batch_id)
        elif ext in MEDIA_EXTS:
            content = process_media(file_path)
        else:
            # Handles Docs, PDFs, Images, Emails, Cache files, etc.
            content = process_standard(file_path)

        if not content:
            return {"status": "completed", "extracted_chunks": 0}

        # DECOUPLED: Enrichment (AI Summarization) is removed from this real-time worker.

        # Advanced Chunking
        chunks = chunk_by_title(content, max_characters=1500)
        texts = [chunk.text for chunk in chunks]

        # Upload
        upload_to_qdrant(texts, file_path, collection, batch_id)
        return {"status": "completed", "extracted_chunks": len(texts)}

    except Exception as e:
        logger.error(f"Critical error processing {file_path}: {e}", exc_info=True)
        # In a production system, implement Dead Letter Queue (DLQ) logic here
        return {"status": "failed", "error": str(e)}


if __name__ == "__main__":
    # Connect to Redis
    redis_conn = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=0)

    # Create and start the worker
    worker = Worker(["high_throughput"], connection=redis_conn)
    logger.info("Starting forensic worker. Listening for jobs...")
    worker.work()
