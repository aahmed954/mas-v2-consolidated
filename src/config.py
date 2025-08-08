import os

class Settings:
    # TogetherAI / embeddings
    TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY", "tgp_v1_peF7JytuY7bC2uMRmsZxglftyn4t2Py4YYXYqDwZzMk")
    TOGETHER_BASE_URL = os.getenv("TOGETHER_BASE_URL", "https://api.together.xyz/v1")
    TOGETHER_EMBEDDING_MODEL = os.getenv("TOGETHER_EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5-vllm")

    # Backends & knobs
    EMBEDDINGS_BACKEND = os.getenv("EMBEDDINGS_BACKEND", "together")  # or "local"
    EMBEDDINGS_L2_NORMALIZE = os.getenv("EMBEDDINGS_L2_NORMALIZE", "false").lower() == "true"
    EMBEDDINGS_MAX_BATCH = int(os.getenv("EMBEDDINGS_MAX_BATCH", "32"))

    # Qdrant
    QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))

    # Safe defaults (env overrides take precedence)
    QDRANT_COLLECTION = os.getenv("COLLECTION", "mas_embeddings")
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")
    OCR_STRATEGY = os.getenv("OCR_STRATEGY", "hi_res")
    ENRICHMENT_LLM_MODEL = os.getenv(
        "ENRICHMENT_LLM_MODEL", "meta-llama-3-70b-instruct"
    )

    # Deprecated batch dir (left here so old paths don't explode)
    BATCH_PROCESSING_DIR = os.path.abspath("./data/batch_processing")

settings = Settings()
