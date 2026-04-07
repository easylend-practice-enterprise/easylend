import asyncio
import importlib
import os
from collections.abc import Awaitable, Iterator
from pathlib import Path
from typing import cast

import pytest
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from alembic import command

# Must be set before importing app settings/main to avoid worker startup side effects.
os.environ.setdefault("ENVIRONMENT", "test")

from app.core.config import settings

API_ROOT = Path(__file__).resolve().parents[3]
POSTGRES_IMAGE = "postgres:17"
REDIS_IMAGE = "redis:7-alpine"
POSTGRES_USER = "test_user"
POSTGRES_PASSWORD = "test_password"  # noqa: S105
POSTGRES_DB = "test_db"


def _run(coro):
    return asyncio.run(coro)


async def _wait_for_postgres(database_url: str) -> None:
    attempts = 40
    delay_seconds = 0.25

    for attempt in range(attempts):
        engine = create_async_engine(
            database_url,
            future=True,
            poolclass=NullPool,
        )
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return
        except Exception:
            if attempt == attempts - 1:
                raise
            await asyncio.sleep(delay_seconds)
            delay_seconds = min(delay_seconds * 1.5, 2.0)
        finally:
            await engine.dispose()


async def _wait_for_redis(redis_client: Redis) -> None:
    attempts = 40
    delay_seconds = 0.25

    for attempt in range(attempts):
        try:
            await cast(Awaitable[bool], redis_client.ping())
            return
        except Exception:
            if attempt == attempts - 1:
                raise
            await asyncio.sleep(delay_seconds)
            delay_seconds = min(delay_seconds * 1.5, 2.0)


async def _truncate_public_tables(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async with session_maker() as session:
        table_result = await session.execute(
            text(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                  AND tablename <> 'alembic_version'
                """
            )
        )
        table_names = list(table_result.scalars().all())

        if table_names:
            quoted_names = ", ".join(f'"{name}"' for name in table_names)
            await session.execute(
                text(f"TRUNCATE TABLE {quoted_names} RESTART IDENTITY CASCADE")
            )

        await session.commit()


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    container = PostgresContainer(
        image=POSTGRES_IMAGE,
        username=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        dbname=POSTGRES_DB,
    )
    with container as running:
        yield running


@pytest.fixture(scope="session")
def redis_container() -> Iterator[RedisContainer]:
    container = RedisContainer(image=REDIS_IMAGE)
    with container as running:
        yield running


@pytest.fixture(scope="session")
def integration_db_url(postgres_container: PostgresContainer) -> str:
    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    database_url = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{host}:{port}/{POSTGRES_DB}"

    _run(_wait_for_postgres(database_url))
    return database_url


@pytest.fixture(scope="session")
def integration_redis_url(redis_container: RedisContainer) -> str:
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}/0"


@pytest.fixture(scope="session", autouse=True)
def configure_integration_settings(
    integration_db_url: str,
    integration_redis_url: str,
) -> Iterator[None]:
    original_db_url = settings.DATABASE_URL
    original_redis_url = settings.REDIS_URL

    settings.DATABASE_URL = integration_db_url
    settings.REDIS_URL = integration_redis_url

    try:
        yield
    finally:
        settings.DATABASE_URL = original_db_url
        settings.REDIS_URL = original_redis_url


@pytest.fixture(scope="session", autouse=True)
def apply_migrations(configure_integration_settings: None) -> Iterator[None]:
    alembic_config = Config(str(API_ROOT / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(API_ROOT / "alembic"))

    command.upgrade(alembic_config, "head")
    yield


@pytest.fixture(scope="session")
def integration_engine(
    integration_db_url: str,
    apply_migrations: None,
) -> Iterator[AsyncEngine]:
    engine = create_async_engine(
        integration_db_url,
        future=True,
        poolclass=NullPool,
    )
    try:
        yield engine
    finally:
        _run(engine.dispose())


@pytest.fixture(scope="session")
def integration_session_maker(
    integration_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        integration_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.fixture(scope="session")
def integration_redis_client(
    integration_redis_url: str,
) -> Iterator[Redis]:
    client = Redis.from_url(
        integration_redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=3,
    )
    _run(_wait_for_redis(client))

    try:
        yield client
    finally:
        _run(client.aclose())


@pytest.fixture(scope="session", autouse=True)
def patch_redis_client_references(
    integration_redis_client: Redis,
) -> Iterator[None]:
    module_names = (
        "app.db.redis",
        "app.core.rate_limit",
        "app.core.redis_utils",
        "app.core.idempotency",
        "app.core.websockets",
    )

    originals: list[tuple[object, Redis]] = []

    for module_name in module_names:
        module = importlib.import_module(module_name)
        if hasattr(module, "redis_client"):
            originals.append((module, getattr(module, "redis_client")))
            setattr(module, "redis_client", integration_redis_client)

    try:
        yield
    finally:
        for module, original in originals:
            setattr(module, "redis_client", original)


@pytest.fixture(autouse=True)
def reset_integration_state(
    integration_session_maker: async_sessionmaker[AsyncSession],
    integration_redis_client: Redis,
) -> Iterator[None]:
    _run(_truncate_public_tables(integration_session_maker))
    _run(integration_redis_client.flushdb())

    try:
        yield
    finally:
        _run(integration_redis_client.flushdb())


@pytest.fixture(scope="session")
def integration_app(
    patch_redis_client_references: None,
) -> FastAPI:
    from app.main import app

    return app


@pytest.fixture()
def app_with_overrides(
    integration_app: FastAPI,
    integration_session_maker: async_sessionmaker[AsyncSession],
) -> Iterator[FastAPI]:
    from app.db.database import get_db

    async def override_get_db():
        async with integration_session_maker() as session:
            yield session

    integration_app.dependency_overrides[get_db] = override_get_db

    try:
        yield integration_app
    finally:
        integration_app.dependency_overrides.clear()


@pytest.fixture()
def client(app_with_overrides: FastAPI) -> Iterator[TestClient]:
    with TestClient(app_with_overrides) as test_client:
        yield test_client
