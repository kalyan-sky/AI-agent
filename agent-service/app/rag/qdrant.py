"""Qdrant client factory.

A single cached client per (url, local_path) pair. Local-mode (embedded,
file-backed) is used when `QDRANT_LOCAL_PATH` is set — convenient for
sandboxed/dev environments without a Qdrant server, at the cost of only
one process being able to open that path at a time. Production points
`QDRANT_URL` at a real server instead and leaves the local path empty.
"""

from functools import lru_cache

from qdrant_client import QdrantClient

from app.config import Settings
from app.testing.failure_injection import should_inject


@lru_cache
def _cached_client(url: str, api_key: str, local_path: str) -> QdrantClient:
    if local_path:
        return QdrantClient(path=local_path)
    return QdrantClient(url=url, api_key=api_key or None)


def get_client(settings: Settings) -> QdrantClient:
    if should_inject(settings, "qdrant_down"):
        raise ConnectionError("injected failure: qdrant_down")
    return _cached_client(settings.qdrant_url, settings.qdrant_api_key, settings.qdrant_local_path)
