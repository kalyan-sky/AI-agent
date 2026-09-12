"""RAG search service backing POST /api/v1/rag/search.

Ingestion (parsing/chunking/embedding runbooks into Qdrant) is built in a
later phase. Until the collection has been populated, `search` returns an
empty result set rather than erroring — a missing collection is an
expected pre-ingestion state, not a failure.
"""
import structlog
from qdrant_client.http import models as qmodels

from app.api.schemas import RagChunkResult, RagSearchRequest, RagSearchResponse
from app.config import Settings
from app.rag.embeddings import embed_texts
from app.rag.qdrant import get_client

logger = structlog.get_logger(__name__)


async def search(request: RagSearchRequest, settings: Settings) -> RagSearchResponse:
    client = get_client(settings)

    if not client.collection_exists(settings.qdrant_collection):
        logger.warning("rag_collection_missing", collection=settings.qdrant_collection)
        return RagSearchResponse(query=request.query, results=[])

    [vector] = embed_texts([request.query], settings.embedding_model)

    hits = client.search(
        collection_name=settings.qdrant_collection,
        query_vector=vector,
        limit=request.top_k,
        query_filter=_build_filter(request),
    )
    results = []
    for hit in hits:
        payload = hit.payload or {}
        results.append(
            RagChunkResult(
                document_id=payload.get("document_id", "unknown"),
                chunk_id=str(hit.id),
                title=payload.get("title", ""),
                text=payload.get("text", ""),
                score=hit.score,
                metadata=payload,
            )
        )
    return RagSearchResponse(query=request.query, results=results)


def _build_filter(request: RagSearchRequest) -> qmodels.Filter | None:
    field_values = {
        "service": request.service,
        "category": request.category,
        "environment": request.environment,
    }
    conditions: list[qmodels.Condition] = [
        qmodels.FieldCondition(key=key, match=qmodels.MatchValue(value=value))
        for key, value in field_values.items()
        if value is not None
    ]
    return qmodels.Filter(must=conditions) if conditions else None
