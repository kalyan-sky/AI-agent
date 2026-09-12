"""RAG service tests, isolated from whatever the dev environment's shared
Qdrant local-mode store happens to contain (it may or may not have had the
real ingestion pipeline run against it). Each test builds its own Settings
pointing at a fresh temp directory so "collection missing" and "collection
populated" are both exercised deterministically.

HTTP-level tests (auth, validation) go through the real app/client since
they don't depend on ingestion state.
"""

import pytest
from qdrant_client.http import models as qmodels

from app.api.schemas import RagSearchRequest
from app.config import Settings
from app.rag.embeddings import embed_texts
from app.rag.qdrant import _cached_client
from app.services import rag_service


@pytest.fixture
def isolated_settings(tmp_path):
    _cached_client.cache_clear()
    settings = Settings(
        qdrant_local_path=str(tmp_path / "qdrant"),
        qdrant_collection="test_collection",
        embedding_provider="local-hash",
        embedding_dim=64,
    )
    yield settings
    _cached_client.cache_clear()


@pytest.mark.asyncio
async def test_search_returns_empty_for_missing_collection(isolated_settings):
    result = await rag_service.search(RagSearchRequest(query="anything"), isolated_settings)
    assert result.results == []


@pytest.mark.asyncio
async def test_search_returns_hits_after_ingestion(isolated_settings):
    from app.rag.qdrant import get_client

    client = get_client(isolated_settings)
    client.create_collection(
        collection_name=isolated_settings.qdrant_collection,
        vectors_config=qmodels.VectorParams(
            size=isolated_settings.embedding_dim, distance=qmodels.Distance.COSINE
        ),
    )
    [vector] = embed_texts(["kubernetes ImagePullBackOff troubleshooting steps"], isolated_settings)
    client.upsert(
        collection_name=isolated_settings.qdrant_collection,
        points=[
            qmodels.PointStruct(
                id=1,
                vector=vector,
                payload={
                    "document_id": "doc1",
                    "title": "K8s guide",
                    "text": "kubernetes ImagePullBackOff troubleshooting steps",
                    "service": "kubernetes",
                },
            )
        ],
    )

    result = await rag_service.search(
        RagSearchRequest(query="ImagePullBackOff", top_k=3), isolated_settings
    )
    assert len(result.results) == 1
    assert result.results[0].document_id == "doc1"


@pytest.mark.asyncio
async def test_search_filters_by_service(isolated_settings):
    from app.rag.qdrant import get_client

    client = get_client(isolated_settings)
    client.create_collection(
        collection_name=isolated_settings.qdrant_collection,
        vectors_config=qmodels.VectorParams(
            size=isolated_settings.embedding_dim, distance=qmodels.Distance.COSINE
        ),
    )
    texts = ["database outage recovery", "database outage recovery"]
    vectors = embed_texts(texts, isolated_settings)
    client.upsert(
        collection_name=isolated_settings.qdrant_collection,
        points=[
            qmodels.PointStruct(
                id=1, vector=vectors[0], payload={"document_id": "d1", "service": "postgres"}
            ),
            qmodels.PointStruct(
                id=2, vector=vectors[1], payload={"document_id": "d2", "service": "payment-service"}
            ),
        ],
    )

    result = await rag_service.search(
        RagSearchRequest(query="database outage", service="postgres", top_k=5),
        isolated_settings,
    )
    assert [r.document_id for r in result.results] == ["d1"]


@pytest.mark.asyncio
async def test_rag_search_requires_auth(client):
    resp = await client.post("/api/v1/rag/search", json={"query": "anything"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_rag_search_rejects_empty_query(client, viewer_headers):
    resp = await client.post("/api/v1/rag/search", headers=viewer_headers, json={"query": ""})
    assert resp.status_code == 422
