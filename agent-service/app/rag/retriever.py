"""Vector retrieval against Qdrant: embed the query, search, filter by metadata.

Kept separate from `services/rag_service.py` so the API-shaped concerns
(schemas, the "collection missing" -> empty-results decision) stay out of
the retrieval mechanism, and so the ingestion pipeline and the agent's
future `search_knowledge` tool can both call this directly.
"""
from qdrant_client.http import models as qmodels

from app.config import Settings
from app.rag.embeddings import embed_texts
from app.rag.qdrant import get_client


def collection_ready(settings: Settings) -> bool:
    return get_client(settings).collection_exists(settings.qdrant_collection)


def search(
    query: str,
    settings: Settings,
    top_k: int = 5,
    service: str | None = None,
    category: str | None = None,
    environment: str | None = None,
) -> list[qmodels.ScoredPoint]:
    client = get_client(settings)
    [vector] = embed_texts([query], settings)
    query_filter = _build_filter(service=service, category=category, environment=environment)
    return client.search(
        collection_name=settings.qdrant_collection,
        query_vector=vector,
        limit=top_k,
        query_filter=query_filter,
    )


def _build_filter(**field_values: str | None) -> qmodels.Filter | None:
    conditions: list[qmodels.Condition] = [
        qmodels.FieldCondition(key=key, match=qmodels.MatchValue(value=value))
        for key, value in field_values.items()
        if value is not None
    ]
    return qmodels.Filter(must=conditions) if conditions else None
