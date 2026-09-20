"""Shared test-database fixtures.

Uses a dedicated `ranahresearch_test` database on the same local PostgreSQL
instance as `make infra-up`. Schema is created once per test session by
running the real Alembic migrations (not `create_all`), so a broken migration
fails the test suite. `DATABASE_URL` is repointed at this database for the
whole process so Temporal activities (which build their own DB session) land
in the same place tests assert against. Each test then runs inside a
savepoint that is rolled back afterwards, so tests never see each other's data.
"""

import os
from collections.abc import AsyncIterator, Iterator

import psycopg
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from ranah_domain.db import create_engine
from ranah_domain.settings import get_settings
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

_TEST_DB_NAME = "ranahresearch_test"


def _admin_url() -> str:
    url = make_url(get_settings().database_url).set(drivername="postgresql")
    return url.set(database="postgres").render_as_string(hide_password=False)


def _test_url() -> str:
    url = make_url(get_settings().database_url).set(database=_TEST_DB_NAME)
    return url.render_as_string(hide_password=False)


@pytest.fixture(scope="session", autouse=True)
def _test_database() -> Iterator[None]:
    with psycopg.connect(_admin_url(), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(f'DROP DATABASE IF EXISTS "{_TEST_DB_NAME}" WITH (FORCE)')
        cur.execute(f'CREATE DATABASE "{_TEST_DB_NAME}"')

    test_url = _test_url()
    config = Config("packages/domain/alembic.ini")
    config.attributes["db_url"] = test_url
    command.upgrade(config, "head")

    # Repoint the whole process at the test database, so activities running
    # inside an in-process Temporal worker write where tests can see it.
    os.environ["DATABASE_URL"] = test_url
    get_settings.cache_clear()
    yield


@pytest_asyncio.fixture(scope="session")
async def db_engine(_test_database: None) -> AsyncIterator[AsyncEngine]:
    engine = create_engine()
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with db_engine.connect() as connection:
        await connection.begin()
        session = AsyncSession(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            await session.close()
            await connection.rollback()
