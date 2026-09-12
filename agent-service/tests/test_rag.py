"""RAG search against the real embedded-mode Qdrant client. No documents have
been ingested yet (that's a later phase), so the meaningful behavior to prove
now is that a missing collection is handled gracefully — empty results, not
an error — rather than the endpoint 500ing until ingestion has run.
"""
import pytest


@pytest.mark.asyncio
async def test_rag_search_returns_empty_before_ingestion(client, viewer_headers):
    resp = await client.post(
        "/api/v1/rag/search",
        headers=viewer_headers,
        json={"query": "kubernetes ImagePullBackOff", "top_k": 3},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == "kubernetes ImagePullBackOff"
    assert body["results"] == []


@pytest.mark.asyncio
async def test_rag_search_requires_auth(client):
    resp = await client.post("/api/v1/rag/search", json={"query": "anything"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_rag_search_rejects_empty_query(client, viewer_headers):
    resp = await client.post(
        "/api/v1/rag/search", headers=viewer_headers, json={"query": ""}
    )
    assert resp.status_code == 422
