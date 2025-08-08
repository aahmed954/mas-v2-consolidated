"""
Embeddings module with automatic failover support.
"""
from .providers import FallbackEmbeddingClient
import math

_fallback_client = FallbackEmbeddingClient()

def get_embeddings(texts, normalize=True):
    """Drop-in replacement with automatic Together→local failover."""
    out = _fallback_client.embed(texts)
    vecs = out["vectors"]
    if normalize:
        # L2 normalize once; Qdrant uses COSINE distance
        nv = []
        for v in vecs:
            s = math.sqrt(sum(x*x for x in v)) or 1.0
            nv.append([x/s for x in v])
        vecs = nv
    return {"provider": out["provider"], "vectors": vecs}

# Re-export for compatibility
from .client import EmbeddingClient
from .models import MODEL_CATALOG

__all__ = ['get_embeddings', 'EmbeddingClient', 'MODEL_CATALOG', 'FallbackEmbeddingClient']