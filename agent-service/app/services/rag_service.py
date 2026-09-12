"""RAG search service backing POST /api/v1/rag/search.

Delegates the actual vector search to app/rag/retriever.py and only
handles the API-shaped decision: a missing collection (nothing ingested
yet) returns an empty result set rather than erroring.
"""
import structlog

from app.api.schemas import RagChunkResult, RagSearchRequest, RagSearchResponse
from app.config import Settings
from app.rag import retriever

logger = structlog.get_logger(__name__)


async def search(request: RagSearchRequest, settings: Settings) -> RagSearchResponse:
    if not retriever.collection_ready(settings):
        logger.warning("rag_collection_missing", collection=settings.qdrant_collection)
        return RagSearchResponse(query=request.query, results=[])

    hits = retriever.search(
        request.query,
        settings,
        top_k=request.top_k,
        service=request.service,
        category=request.category,
        environment=request.environment,
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
