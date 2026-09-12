"""RAG search service backing POST /api/v1/rag/search.

Delegates the actual vector search to app/rag/retriever.py and handles two
API-shaped decisions: a missing collection (nothing ingested yet) or an
unreachable Qdrant server both return an empty result set rather than
erroring — this endpoint is called both directly (e.g. an n8n workflow
step) and, via the agent's search_knowledge tool, from inside an incident
investigation, and neither caller should hard-fail just because the
knowledge base happens to be unavailable for one call.
"""

import structlog

from app.api.schemas import RagChunkResult, RagSearchRequest, RagSearchResponse
from app.config import Settings
from app.rag import retriever

logger = structlog.get_logger(__name__)


async def search(request: RagSearchRequest, settings: Settings) -> RagSearchResponse:
    try:
        collection_ready = retriever.collection_ready(settings)
    except Exception as exc:  # noqa: BLE001 - Qdrant down degrades to no results, not a 500
        logger.error("qdrant_unavailable", collection=settings.qdrant_collection, error=str(exc))
        return RagSearchResponse(query=request.query, results=[])

    if not collection_ready:
        logger.warning("rag_collection_missing", collection=settings.qdrant_collection)
        return RagSearchResponse(query=request.query, results=[])

    try:
        hits = retriever.search(
            request.query,
            settings,
            top_k=request.top_k,
            service=request.service,
            category=request.category,
            environment=request.environment,
        )
    except Exception as exc:  # noqa: BLE001 - same as above: degrade, don't 500
        logger.error("qdrant_unavailable", collection=settings.qdrant_collection, error=str(exc))
        return RagSearchResponse(query=request.query, results=[])

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
