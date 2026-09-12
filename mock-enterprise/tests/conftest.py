import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.scenarios import reset_scenarios


@pytest_asyncio.fixture
async def client():
    reset_scenarios()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    reset_scenarios()
