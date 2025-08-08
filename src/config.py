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

    # Deprecated batch dir (left here so old paths don't explode)
    BATCH_PROCESSING_DIR = os.path.abspath("./data/batch_processing")

settings = Settings()
