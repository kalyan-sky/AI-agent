import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


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
