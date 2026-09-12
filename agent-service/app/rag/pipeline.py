"""RAG ingestion pipeline: documents -> chunks -> embeddings -> Qdrant.

Run via `python -m app.rag.pipeline` (wired to `make rag-ingest`).
Idempotent: drops and recreates the collection each run so re-ingesting
after editing a runbook never leaves stale chunks behind.
"""
import logging
from pathlib import Path

import structlog
from qdrant_client.http import models as qmodels

from app.config import Settings, get_settings
from app.rag.chunker import chunk_text
from app.rag.embeddings import embed_texts
from app.rag.loader import load_documents
from app.rag.qdrant import get_client

logger = structlog.get_logger(__name__)

DEFAULT_DOCUMENTS_DIR = Path(__file__).resolve().parents[3] / "rag" / "documents"


def run(documents_dir: Path | None = None, settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    documents_dir = documents_dir or DEFAULT_DOCUMENTS_DIR
    documents = load_documents(documents_dir)
    logger.info("rag_ingest_loaded", count=len(documents), directory=str(documents_dir))

    client = get_client(settings)
    if client.collection_exists(settings.qdrant_collection):
        client.delete_collection(settings.qdrant_collection)
    client.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config=qmodels.VectorParams(
            size=settings.embedding_dim, distance=qmodels.Distance.COSINE
        ),
    )

    points = []
    point_id = 0
    for doc in documents:
        chunks = chunk_text(
            doc.document_id, doc.text, settings.rag_chunk_size, settings.rag_chunk_overlap
        )
        vectors = embed_texts([c.text for c in chunks], settings)
        for chunk, vector in zip(chunks, vectors, strict=True):
            points.append(
                qmodels.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "document_id": doc.document_id,
                        "chunk_id": chunk.chunk_id,
                        "title": doc.title,
                        "category": doc.category,
                        "service": doc.service,
                        "environment": doc.environment,
                        "source": doc.source,
                        "text": chunk.text,
                    },
                )
            )
            point_id += 1

    if points:
        client.upsert(collection_name=settings.qdrant_collection, points=points)
    logger.info("rag_ingest_complete", chunks=len(points), collection=settings.qdrant_collection)
    return len(points)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ingested = run()
    print(f"Ingested {ingested} chunks into '{get_settings().qdrant_collection}'.")
