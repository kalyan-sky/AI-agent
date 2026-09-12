import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.database.session import _cached_engine
from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


TEST_DATABASE_URL = "postgresql+asyncpg://aiops:devpassword@127.0.0.1:5432/aiops"


@pytest_asyncio.fixture(autouse=True)
async def _reset_db_engine_cache_per_test():
    """pytest-asyncio gives each test its own event loop, but
    `_cached_engine` is `lru_cache`d (deliberately, for production, where
    one process = one long-lived loop) — so an engine built in one test
    outlives its loop, and the next test's asyncpg calls fail with
    "Future attached to a different loop". Dispose + clear on this test's
    own (still-alive) loop before it closes, so the next test builds a
    fresh engine bound to its own new loop.
    """
    yield
    # Calling _cached_engine again for a URL a test already used is a cache
    # hit (returns the same engine, doesn't create a new one) — this is
    # just how we retrieve it for disposal since lru_cache doesn't expose
    # its stored values directly.
    await _cached_engine(TEST_DATABASE_URL).dispose()
    _cached_engine.cache_clear()


def _first_key_for_role(role: str) -> str:
    settings = get_settings()
    for entry in settings.api_keys.split(","):
        key, _, entry_role = entry.strip().partition(":")
        if entry_role == role:
            return key
    raise RuntimeError(f"no configured API key for role={role!r}; check agent-service/.env")


@pytest.fixture
def viewer_headers() -> dict:
    return {"Authorization": f"Bearer {_first_key_for_role('viewer')}"}


@pytest.fixture
def operator_headers() -> dict:
    return {"Authorization": f"Bearer {_first_key_for_role('operator')}"}


@pytest.fixture
def admin_headers() -> dict:
    return {"Authorization": f"Bearer {_first_key_for_role('admin')}"}


@pytest.fixture
def anyio_backend():
    return "asyncio"
