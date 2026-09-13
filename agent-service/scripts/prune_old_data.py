"""Retention/pruning for old conversations (and, via cascade, their
messages, agent executions, tool executions, and decided approvals) —
`make prune` / `python -m scripts.prune_old_data`.

This is a human-invoked runbook step, deliberately never a scheduled
job: deleting audit-trail data is a destructive, irreversible action,
and per this project's own risk-tier policy (a CRITICAL action is never
autonomous, HIGH_RISK always needs a human decision) the same principle
applies to operating on the platform itself, not just what the agent
does. Concretely:

  - No flags at all: DRY RUN. Reports what would be deleted, deletes
    nothing. Safe to run any time, by anyone, including from a script.
  - --confirm: still reports the same thing, then requires typing the
    exact live count back at an interactive prompt before anything is
    deleted — not just a --yes flag a cron job could pass unattended.
    Refuses outright if stdin isn't a TTY, so this can't accidentally be
    wired into automation even by someone trying to.

Conversations with a still-pending approval are excluded regardless of
age (see app/memory/repository.py::list_conversations_older_than) —
deleting one would destroy the audit trail for a HIGH_RISK action a
human hasn't decided on yet.
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.database.session import get_session_factory
from app.memory import repository


async def _report(older_than_days: int) -> list:
    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    session_factory = get_session_factory(settings)
    async with session_factory() as session:
        conversations = await repository.list_conversations_older_than(session, cutoff)

    print(f"Cutoff: conversations with no activity since {cutoff.isoformat()}")
    print(f"Found {len(conversations)} conversation(s) eligible for deletion:")
    for c in conversations[:20]:
        print(
            f"  - {c.conversation_id} (user={c.user_id}, "
            f"last activity={c.updated_at.isoformat()})"
        )
    if len(conversations) > 20:
        print(f"  ... and {len(conversations) - 20} more")
    return conversations


async def _delete(conversations: list) -> None:
    settings = get_settings()
    session_factory = get_session_factory(settings)
    async with session_factory() as session:
        for c in conversations:
            await repository.delete_conversation(session, c)
        await session.commit()


async def _amain(argv: list[str]) -> int:
    """The real logic, as a single coroutine — kept separate from main()
    so tests can `await` it directly inside their own event loop instead
    of going through main()'s asyncio.run(), which can't nest inside
    pytest-asyncio's already-running loop (and, worse, would reuse the
    lru_cache'd DB engine across a different event loop per call within
    one test — the exact bug tests/conftest.py's engine-cache-reset
    fixture exists to prevent elsewhere)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--older-than-days",
        type=int,
        default=90,
        help="Delete conversations with no activity in at least this many days (default: 90).",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually delete (after an interactive confirmation) instead of a dry run.",
    )
    args = parser.parse_args(argv)

    conversations = await _report(args.older_than_days)

    if not args.confirm:
        print("\nDRY RUN — nothing was deleted. Re-run with --confirm to actually delete.")
        return 0

    if not conversations:
        print("\nNothing to delete.")
        return 0

    if not sys.stdin.isatty():
        print(
            "\nRefusing to delete: --confirm requires an interactive terminal, "
            "not a script or scheduled job. This is deliberate — see this file's docstring.",
            file=sys.stderr,
        )
        return 1

    answer = input(
        f"\nType {len(conversations)} (the exact count above) to permanently delete "
        "these conversations, or anything else to abort: "
    )
    if answer.strip() != str(len(conversations)):
        print("Aborted — no changes made.")
        return 1

    await _delete(conversations)
    print(f"Deleted {len(conversations)} conversation(s).")
    return 0


def main() -> int:
    return asyncio.run(_amain(sys.argv[1:]))


if __name__ == "__main__":
    sys.exit(main())
