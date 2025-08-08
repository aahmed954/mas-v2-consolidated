import os, time, json, logging, requests
from typing import List, Tuple
import numpy as np

from .models import get_model_meta

logger = logging.getLogger(__name__)

LOCAL_SUPPORTED = {
    "BAAI/bge-base-en-v1.5-vllm": "BAAI/bge-base-en-v1.5",
    "BAAI/bge-large-en-v1.5": "BAAI/bge-large-en-v1.5",
    "Alibaba-NLP/gte-modernbert-base": "Alibaba-NLP/gte-modernbert-base",
    "intfloat/multilingual-e5-large-instruct": "intfloat/multilingual-e5-large-instruct",
    # togethercomputer/m2-bert-* not available as HF sentence-transformers model
}

class EmbeddingClient:
    def __init__(self, api_key: str, base_url: str, model: str, backend: str = "together",
                 l2_normalize: bool = False, max_batch: int = 32, timeout_s: int = 60, max_retries: int = 5):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = get_model_meta(model).name
        self.meta = get_model_meta(self.model)
        self.backend = backend
        self.l2_normalize = l2_normalize
        self.max_batch = max_batch
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self._local_model = None
        if backend not in ("together","local"):
            raise NotImplementedError("backend must be 'together' or 'local'")
        if backend == "together" and not self.api_key:
            raise RuntimeError("TOGETHER_API_KEY is empty.")
        if backend == "local":
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore
                hf_name = LOCAL_SUPPORTED.get(self.model)
                if not hf_name:
                    raise RuntimeError(f"Local backend does not support model {self.model}")
                # Let ST handle device selection; supports CUDA on 4090
                self._local_model = SentenceTransformer(hf_name)
            except Exception as e:
                raise RuntimeError(f"Failed to init local embeddings: {e}")

    def _approx_truncate(self, text: str) -> str:
        # Rough heuristic: 1 token ~ 4 chars average for English
        max_chars = self.meta.max_tokens * 4
        return text if len(text) <= max_chars else text[:max_chars]

    def _chunks(self, xs: List[str], n: int):
        for i in range(0, len(xs), n):
            yield xs[i:i+n]

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.base_url}{path}"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        delay = 1.0
        for attempt in range(1, self.max_retries + 1):
            t0 = time.time()
            resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=self.timeout_s)
            latency = time.time() - t0
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (429, 500, 502, 503, 504):
                logger.warning(f"Embeddings POST retry {attempt}/{self.max_retries} (status {resp.status_code}) after {latency:.2f}s")
                time.sleep(delay)
                delay = min(delay * 2, 30)
                # simple adaptive batch shrink on trouble
                self.max_batch = max(4, int(self.max_batch/2))
                continue
            raise RuntimeError(f"Embeddings error {resp.status_code}: {resp.text[:500]}")
        raise RuntimeError("Embeddings failed after max retries.")

    def embed_texts(self, texts: List[str]) -> Tuple[List[List[float]], int]:
        if not texts:
            return [], 0
        # Token-aware truncation (heuristic) to stay under model limits
        texts = [self._approx_truncate(t) for t in texts]

        vectors: List[List[float]] = []
        total_tokens = 0

        if self.backend == "local":
            # sentence-transformers returns numpy array
            arr = self._local_model.encode(texts, batch_size=self.max_batch, show_progress_bar=False, convert_to_numpy=True, normalize_embeddings=self.l2_normalize)  # type: ignore
            vectors = arr.tolist()
            return vectors, 0

        for batch in self._chunks(texts, self.max_batch):
            payload = {"model": self.model, "input": batch}
            t0 = time.time()
            data = self._post("/embeddings", payload)
            latency = time.time() - t0
            batch_vecs = [item["embedding"] for item in data.get("data", [])]
            if self.l2_normalize and batch_vecs:
                arr = np.asarray(batch_vecs, dtype=np.float32)
                norms = np.linalg.norm(arr, axis=1, keepdims=True) + 1e-12
                arr = arr / norms
                batch_vecs = arr.tolist()
            vectors.extend(batch_vecs)
            usage = data.get("usage") or {}
            total_tokens += int(usage.get("prompt_tokens", 0))
            logger.info(f"Embedded {len(batch)} items; tokens={usage.get('prompt_tokens','n/a')}; dim={len(batch_vecs[0]) if batch_vecs else 'n/a'}; latency={latency:.2f}s")

            # Light adaptive tuning: if latency > 3s and batch>8, reduce; if <0.6s, maybe raise a bit (cap at 64)
            if latency > 3.0 and self.max_batch > 8:
                self.max_batch = max(8, int(self.max_batch * 0.75))
            elif latency < 0.6 and self.max_batch < 64:
                self.max_batch = min(64, int(self.max_batch + 4))

        exp = self.meta.dim
        if vectors and len(vectors[0]) != exp:
            raise RuntimeError(f"Embedding dimension mismatch: expected {exp}, got {len(vectors[0])}")
        return vectors, total_tokens
