"""Direct repository tests against a real Postgres — the module docstring
in app/memory/repository.py explains why plain functions over a session
rather than a class; these exercise the ones not already covered
end-to-end via agent_service.run in tests/test_agent.py.
"""

import asyncio

import pytest

from app.config import Settings
from app.database.session import get_session_factory
from app.memory import repository

DATABASE_URL = "postgresql+asyncpg://aiops:devpassword@127.0.0.1:5432/aiops"


def _settings() -> Settings:
    return Settings(database_url=DATABASE_URL)


@pytest.mark.asyncio
async def test_get_or_create_conversation_bumps_updated_at_on_existing_rows():
    """Regression: updated_at used to be set only at creation and never
    touched again, so it reflected "when this conversation started",
    not "when it was last active" — exactly the signal a retention
    policy (scripts/prune_old_data.py) needs to not be wrong about."""
    session_factory = get_session_factory(_settings())
    conversation_id = "test-updated-at-bump"

    async with session_factory() as session:
        first = await repository.get_or_create_conversation(session, conversation_id, "u1")
        await session.commit()
        first_updated_at = first.updated_at

    await asyncio.sleep(0.05)

    async with session_factory() as session:
        second = await repository.get_or_create_conversation(session, conversation_id, "u1")
        await session.commit()
        second_updated_at = second.updated_at

    assert second.id == first.id  # same row, not a duplicate
    assert second_updated_at > first_updated_at
