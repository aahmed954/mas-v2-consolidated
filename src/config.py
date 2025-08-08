import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    # Redis (Local on Starlord)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6380

    # Qdrant (Local on Starlord)
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "forensic_consolidated_v1")

    # Together.AI
    TOGETHER_API_KEY: str = os.getenv("TOGETHER_API_KEY", "")
    # Pipeline A: Real-time embeddings (E5-Large for multilingual support)
    TOGETHER_EMBEDDING_MODEL: str = "intfloat/multilingual-e5-large-instruct"

    # Pipeline B: Batch API Enrichment Model (Must be supported by Batch API)
    TOGETHER_LLM_MODEL: str = "meta-llama/Llama-3-70b-chat-hf"

    # Directory for JSONL files (Batch API) - Stored locally on Starlord
    BATCH_PROCESSING_DIR: str = os.path.abspath("./data/batch_processing")

    # Processing (RTX 4090 utilization)
    WHISPER_MODEL_SIZE: str = "large-v3"
    OCR_STRATEGY: str = "hi_res"  # Ensures GPU-based PaddleOCR

    class Config:
        env_file = ".env"


settings = Settings()
