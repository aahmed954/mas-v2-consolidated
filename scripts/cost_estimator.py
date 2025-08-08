import os, sys; sys.path.append(os.path.dirname(os.path.dirname(__file__)))
#!/usr/bin/env python3
import sys
from src.embeddings.models import get_model_meta

PRICE_PER_MILLION = {
    "BAAI/bge-base-en-v1.5-vllm": 0.008,
    "togethercomputer/m2-bert-80M-32k-retrieval": 0.008,
    "BAAI/bge-large-en-v1.5": 0.016,
    "intfloat/multilingual-e5-large-instruct": 0.020,
    "Alibaba-NLP/gte-modernbert-base": 0.080,
}

def main():
    if len(sys.argv) != 2 and len(sys.argv) != 3:
        print("Usage: python scripts/cost_estimator.py <model_name> <num_tokens>")
        raise SystemExit(1)
    model = sys.argv[1]
    tokens = int(sys.argv[2]) if len(sys.argv) == 3 else 0
    meta = get_model_meta(model)
    price = PRICE_PER_MILLION.get(meta.name)
    if price is None:
        print(f"No price configured for {meta.name}.")
        raise SystemExit(2)
    cost = (tokens / 1_000_000) * price
    print(f"Model: {meta.name}\nTokens: {tokens:,}\nEst. cost: ${cost:0.6f}")

if __name__ == "__main__":
    main()
