#!/usr/bin/env python3
import os, sys; sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import time
from src.embeddings.client import EmbeddingClient
from src.config import settings

# Skip m2-bert if requested
if os.getenv("SKIP_M2BERT"):
    from src.embeddings.models import MODEL_CATALOG as _CAT
    MODEL_CATALOG = {k:v for k,v in _CAT.items() if "m2-bert" not in k}
else:
    from src.embeddings.models import MODEL_CATALOG

def check(model: str):
    client = EmbeddingClient(
        api_key=settings.TOGETHER_API_KEY,
        base_url=settings.TOGETHER_BASE_URL,
        model=model,
        max_batch=8,
    )
    samples = ["Hello world", "MAS V2 healthcheck", "Vector test 123"]
    t0 = time.time()
    vecs, tokens = client.embed_texts(samples)
    dt = time.time() - t0
    dim = len(vecs[0]) if vecs else 0
    print(f"{model:40} OK  dim={dim:4} n={len(samples)} tokens={tokens} latency={dt:.2f}s")

def main():
    print("TogetherAI Embedding Healthcheck\n")
    failed = False
    for name in MODEL_CATALOG:
        try:
            check(name)
        except Exception as e:
            failed = True
            print(f"{name:40} FAILED {e}")
    if failed:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
