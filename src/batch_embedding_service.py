"""
Deprecated: batch_embedding_service replaced by src.embeddings.client. 
Kept as shim to avoid import explosions.
"""
from logging import getLogger
logger = getLogger(__name__)
logger.warning("Use EmbeddingClient from src.embeddings.client instead of batch_embedding_service.")

class _Noop:
    def embed_texts(self, texts):
        raise RuntimeError("batch_embedding_service is deprecated.")

embedding_service = _Noop()
