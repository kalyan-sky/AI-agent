"""Hugging Face embedding provider.

The model is loaded lazily (and cached) on first use so importing this
module — or starting the API before any RAG document has been ingested —
never pays the model-load cost. Swapping `EMBEDDING_MODEL` is a config
change; nothing else in the codebase names a specific model.
"""
from functools import lru_cache


@lru_cache
def _model(model_name: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def embed_texts(texts: list[str], model_name: str) -> list[list[float]]:
    model = _model(model_name)
    return model.encode(texts, normalize_embeddings=True).tolist()
