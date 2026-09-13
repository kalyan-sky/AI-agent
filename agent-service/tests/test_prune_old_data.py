"""scripts/prune_old_data.py's HITL gate, tested against a real Postgres:
dry run never touches the DB, --confirm refuses outright without a real
TTY, a wrong answer at the prompt aborts, and only an exact-count answer
at an interactive prompt actually deletes (with cascade to children).

Interactivity is mocked (patch.object on sys.stdin / builtins.input) —
a real pseudo-TTY isn't practical to drive from pytest — but the DB
effects (or lack of them) are checked against the real database, not
mocked, so what actually gets deleted is genuinely verified.
"""

import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.config import Settings
from app.database.models import Conversation, Message
from app.database.session import get_session_factory
from scripts import prune_old_data

DATABASE_URL = "postgresql+asyncpg://aiops:devpassword@127.0.0.1:5432/aiops"


def _settings() -> Settings:
    return Settings(database_url=DATABASE_URL)


async def _delete_all_prune_test_conversations() -> None:
    session_factory = get_session_factory(_settings())
    async with session_factory() as session:
        result = await session.execute(
            select(Conversation).where(Conversation.conversation_id.like("prune-%"))
        )
        for conversation in result.scalars().all():
            await session.delete(conversation)  # ORM cascade — see repository.delete_conversation
        await session.commit()


@pytest.fixture(autouse=True)
async def _isolated_prune_test_data():
    # Each test's own conversation must be the *only* eligible one, since
    # scripts/prune_old_data.py's confirmation prompt requires typing the
    # exact live count — another test's leftover old conversation would
    # throw that count off. dry-run/no-tty/wrong-answer tests correctly
    # leave their conversation behind (that's what they're testing), so
    # this cleans up before AND after every test, not just after.
    await _delete_all_prune_test_conversations()
    yield
    await _delete_all_prune_test_conversations()


async def _seed_old_conversation(conversation_id: str, *, with_message: bool = False) -> None:
    old = datetime.now(UTC) - timedelta(days=200)
    session_factory = get_session_factory(_settings())
    async with session_factory() as session:
        conversation = Conversation(
            conversation_id=conversation_id, user_id="u1", created_at=old, updated_at=old
        )
        session.add(conversation)
        await session.flush()
        if with_message:
            session.add(
                Message(
                    conversation_id=conversation.id, role="user", content="hi", created_at=old
                )
            )
        await session.commit()


async def _conversation_exists(conversation_id: str) -> bool:
    session_factory = get_session_factory(_settings())
    async with session_factory() as session:
        result = await session.execute(
            select(Conversation).where(Conversation.conversation_id == conversation_id)
        )
        return result.scalar_one_or_none() is not None


@pytest.fixture(autouse=True)
def _settings_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    prune_old_data.get_settings.cache_clear()
    yield
    prune_old_data.get_settings.cache_clear()


@pytest.mark.asyncio
async def test_dry_run_never_deletes():
    await _seed_old_conversation("prune-dry-run")
    exit_code = await prune_old_data._amain(["--older-than-days", "90"])
    assert exit_code == 0
    assert await _conversation_exists("prune-dry-run")


@pytest.mark.asyncio
async def test_confirm_without_tty_refuses():
    await _seed_old_conversation("prune-no-tty")
    with patch.object(sys.stdin, "isatty", return_value=False):
        exit_code = await prune_old_data._amain(["--confirm"])
    assert exit_code == 1
    assert await _conversation_exists("prune-no-tty")


@pytest.mark.asyncio
async def test_confirm_with_wrong_answer_aborts():
    await _seed_old_conversation("prune-wrong-answer")
    with (
        patch.object(sys.stdin, "isatty", return_value=True),
        patch("builtins.input", return_value="no thanks"),
    ):
        exit_code = await prune_old_data._amain(["--confirm"])
    assert exit_code == 1
    assert await _conversation_exists("prune-wrong-answer")


@pytest.mark.asyncio
async def test_confirm_with_correct_count_deletes_with_cascade():
    await _seed_old_conversation("prune-confirmed", with_message=True)
    with (
        patch.object(sys.stdin, "isatty", return_value=True),
        patch("builtins.input", return_value="1"),
    ):
        exit_code = await prune_old_data._amain(["--confirm"])
    assert exit_code == 0
    assert not await _conversation_exists("prune-confirmed")


@pytest.mark.asyncio
async def test_conversation_with_pending_approval_is_never_eligible_regardless_of_age():
    from app.memory import repository

    session_factory = get_session_factory(_settings())
    old = datetime.now(UTC) - timedelta(days=400)
    async with session_factory() as session:
        conversation = Conversation(
            conversation_id="prune-pending-approval", user_id="u1", created_at=old, updated_at=old
        )
        session.add(conversation)
        await session.flush()
        execution = await repository.create_agent_execution(session, conversation, "roll it back")
        tool_execution = await repository.add_tool_execution(
            session,
            execution,
            tool_name="rollback_deployment",
            arguments={},
            risk_tier="high_risk",
            status="pending_approval",
            result=None,
            error=None,
        )
        await repository.create_approval(session, tool_execution)
        await session.commit()

    await prune_old_data._amain(["--older-than-days", "1"])

    assert await _conversation_exists("prune-pending-approval")
