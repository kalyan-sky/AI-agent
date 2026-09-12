"""Embedding provider abstraction.

Two providers, selected by `EMBEDDING_PROVIDER` — a config change, never a
code change at any call site:

- "huggingface" (default, recommended): `sentence-transformers`, loaded
  from the Hugging Face Hub (or its local cache after the first run) on
  CPU. Requires normal internet egress the first time it runs.
- "local-hash": a deterministic, dependency-free hashing embedding with
  zero network calls, zero downloads. It has no real semantic
  generalization (no learned representation — just a stable bag-of-hashed-
  tokens vector) and exists only as a fallback for network-restricted
  environments where huggingface.co isn't reachable (some sandboxes block
  it the same way they block Docker Hub). It's what lets the ingestion +
  retrieval *mechanism* (chunking, filtering, Qdrant storage, scoring) be
  exercised end to end without external network access — it is not a
  substitute for real embeddings in an actual deployment.
"""
import hashlib
from functools import lru_cache

from app.config import Settings


@lru_cache
def _hf_model(model_name: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def embed_texts(texts: list[str], settings: Settings) -> list[list[float]]:
    if settings.embedding_provider == "local-hash":
        return [_hash_embed(text, settings.embedding_dim) for text in texts]
    model = _hf_model(settings.embedding_model)
    return model.encode(texts, normalize_embeddings=True).tolist()


def _hash_embed(text: str, dim: int) -> list[float]:
    vector = [0.0] * dim
    for token in text.lower().split():
        digest = hashlib.md5(token.encode("utf-8"), usedforsecurity=False).hexdigest()
        vector[int(digest, 16) % dim] += 1.0
    norm = sum(v * v for v in vector) ** 0.5
    if norm > 0:
        vector = [v / norm for v in vector]
    return vector
