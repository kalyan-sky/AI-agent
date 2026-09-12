"""Async SQLAlchemy engine/session factory, cached per database URL so
each request doesn't pay to rebuild a connection pool.
"""

from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings


@lru_cache
def _cached_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)


def get_session_factory(settings: Settings) -> async_sessionmaker[AsyncSession]:
    engine = _cached_engine(settings.database_url)
    return async_sessionmaker(engine, expire_on_commit=False)
