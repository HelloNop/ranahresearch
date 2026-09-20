"""Async SQLAlchemy engine/session plumbing. PostgreSQL is the source of truth."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from ranah_domain.settings import get_settings


class Base(DeclarativeBase):
    pass


def create_engine(database_url: str | None = None, *, echo: bool | None = None) -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        database_url or settings.database_url,
        echo=settings.database_echo if echo is None else echo,
        pool_pre_ping=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Commit on success, roll back on error."""
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
