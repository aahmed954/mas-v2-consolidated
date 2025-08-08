from dataclasses import dataclass
from typing import Dict

@dataclass(frozen=True)
class ModelMeta:
    name: str
    dim: int
    max_tokens: int

MODEL_CATALOG: Dict[str, ModelMeta] = {
    "BAAI/bge-base-en-v1.5-vllm": ModelMeta("BAAI/bge-base-en-v1.5-vllm", 768, 512),
    "BAAI/bge-large-en-v1.5": ModelMeta("BAAI/bge-large-en-v1.5", 1024, 512),
    "togethercomputer/m2-bert-80M-32k-retrieval": ModelMeta("togethercomputer/m2-bert-80M-32k-retrieval", 768, 32768),
    "Alibaba-NLP/gte-modernbert-base": ModelMeta("Alibaba-NLP/gte-modernbert-base", 768, 8192),
    "intfloat/multilingual-e5-large-instruct": ModelMeta("intfloat/multilingual-e5-large-instruct", 1024, 514),
}

def get_model_meta(name: str) -> ModelMeta:
    if name not in MODEL_CATALOG:
        if name == "BAAI/bge-base-en-v1.5":
            return MODEL_CATALOG["BAAI/bge-base-en-v1.5-vllm"]
        raise KeyError(f"Unknown embedding model '{name}'. Valid: {list(MODEL_CATALOG)}")
    return MODEL_CATALOG[name]
