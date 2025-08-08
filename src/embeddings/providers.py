import os, time, threading, requests, random
from typing import List, Dict, Any, Optional

TOGETHER_URL = os.getenv("TOGETHER_BASE_URL", "https://api.together.xyz/v1/embeddings")
LOCAL_URL    = os.getenv("LOCAL_EMBED_URL",  "http://127.0.0.1:8085/embeddings")
MODEL_ID     = os.getenv("MODEL_ID", "BAAI/bge-base-en-v1.5-vllm")
TIMEOUT_S    = float(os.getenv("EMBED_TIMEOUT_S", "30"))

class CircuitBreaker:
    def __init__(self, fail_threshold=3, success_threshold=2, cool_seconds=20):
        self.fail_threshold = fail_threshold
        self.success_threshold = success_threshold
        self.cool_seconds = cool_seconds
        self._state = "primary"  # "primary" or "fallback"
        self._fails = 0
        self._succ  = 0
        self._lock = threading.Lock()

    def on_success(self):
        with self._lock:
            self._fails = 0
            if self._state == "fallback":
                self._succ += 1
                if self._succ >= self.success_threshold:
                    self._state = "primary"
                    self._succ = 0
            else:
                self._succ = 0

    def on_failure(self):
        with self._lock:
            self._fails += 1
            self._succ = 0
            if self._fails >= self.fail_threshold:
                self._state = "fallback"
                self._fails = 0

    @property
    def using_primary(self):
        with self._lock:
            return self._state == "primary"

class FallbackEmbeddingClient:
    def __init__(self):
        self.cb = CircuitBreaker(
            fail_threshold=int(os.getenv("EMBED_FAIL_THRESHOLD", "3")),
            success_threshold=int(os.getenv("EMBED_SUCCESS_THRESHOLD", "2")),
            cool_seconds=int(os.getenv("EMBED_COOL_SECONDS", "20")),
        )
        self._api_key = os.getenv("TOGETHER_API_KEY","")
        # background pinger to bring us back to Together when it recovers
        t = threading.Thread(target=self._pinger, daemon=True)
        t.start()

    def _pinger(self):
        while True:
            time.sleep(10)
            if not self.cb.using_primary:
                try:
                    self._call_together(["ping"])
                    self.cb.on_success()
                except Exception:
                    # still down; keep waiting
                    pass

    def _call_together(self, texts: List[str]) -> List[List[float]]:
        hdr = {"Authorization": f"Bearer {self._api_key}", "Content-Type":"application/json"}
        body = {"model": MODEL_ID, "input": texts, "encoding_format": "float"}
        r = requests.post(TOGETHER_URL, json=body, headers=hdr, timeout=TIMEOUT_S)
        if r.status_code >= 400:
            # treat 429/5xx as hard failures to trigger fallback
            raise RuntimeError(f"Together {r.status_code}: {r.text[:200]}")
        data = r.json()["data"]
        return [row["embedding"] for row in data]

    def _call_local(self, texts: List[str]) -> List[List[float]]:
        body = {"input": texts, "model": "BAAI/bge-base-en-v1.5"}  # TEI ignores model field but it's fine
        r = requests.post(LOCAL_URL, json=body, timeout=TIMEOUT_S)
        if r.status_code >= 400:
            raise RuntimeError(f"Local TEI {r.status_code}: {r.text[:200]}")
        data = r.json()["data"]
        return [row["embedding"] for row in data]

    def embed(self, texts: List[str]) -> Dict[str, Any]:
        # simple jittered retry on current lane; if fails, flip lanes and retry once
        lane = "together" if self.cb.using_primary else "local"
        providers = [lane, "local" if lane=="together" else "together"]
        last_err = None
        for i, which in enumerate(providers):
            try:
                if which == "together":
                    vecs = self._call_together(texts)
                    self.cb.on_success()
                    return {"provider":"together","vectors":vecs}
                else:
                    vecs = self._call_local(texts)
                    # note: success on local does not change breaker back
                    return {"provider":"local","vectors":vecs}
            except Exception as e:
                last_err = e
                if which == "together":
                    self.cb.on_failure()
                # tiny backoff
                time.sleep(0.5 + random.random())
        raise RuntimeError(f"Both providers failed; last: {last_err}")