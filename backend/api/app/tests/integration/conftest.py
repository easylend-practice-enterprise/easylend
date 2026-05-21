import importlib

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from app.core.config import settings
from app.db.database import get_db
from app.db.models import Base
from app.main import app


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:17-alpine") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def redis_container():
    with RedisContainer("redis:7-alpine") as redis:
        yield redis


@pytest_asyncio.fixture(scope="session", autouse=True)
async def override_settings(postgres_container, redis_container):
    # Retrieve dynamic connection URLs
    db_url = postgres_container.get_connection_url().replace("psycopg2", "asyncpg")
    redis_host = redis_container.get_container_host_ip()
    redis_port = redis_container.get_exposed_port(6379)
    redis_url = f"redis://{redis_host}:{redis_port}/0"

    # Override Pydantic settings
    settings.DATABASE_URL = db_url
    settings.REDIS_URL = redis_url

    yield


@pytest_asyncio.fixture(scope="session")
async def integration_engine(override_settings):
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield engine
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def reset_integration_state(integration_engine):
    async with integration_engine.begin() as conn:
        table_result = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        table_names = list(table_result.scalars().all())
        # Filter out alembic_version if present, though create_all doesn't create it
        table_names = [name for name in table_names if name != "alembic_version"]
        if table_names:
            quoted_names = ", ".join(f'"{name}"' for name in table_names)
            await conn.execute(
                text(f"TRUNCATE TABLE {quoted_names} RESTART IDENTITY CASCADE")
            )


@pytest_asyncio.fixture
async def integration_db_session(integration_engine):
    AsyncSessionLocal = async_sessionmaker(
        bind=integration_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def integration_redis_client(override_settings):
    import redis.asyncio as redis_async

    client = redis_async.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    yield client
    await client.flushall()
    await client.aclose()


@pytest_asyncio.fixture
async def async_client(integration_db_session):
    def _get_db_override():
        yield integration_db_session

    app.dependency_overrides[get_db] = _get_db_override
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function", autouse=True)
async def patch_redis_client_references(integration_redis_client):
    module_names = (
        "app.db.redis",
        "app.core.rate_limit",
        "app.core.redis_utils",
        "app.core.idempotency",
        "app.core.websockets",
    )
    originals = []
    for module_name in module_names:
        try:
            module = importlib.import_module(module_name)
            if hasattr(module, "redis_client"):
                originals.append((module, getattr(module, "redis_client")))
                setattr(module, "redis_client", integration_redis_client)
        except ImportError:
            continue

    yield

    for module, original in originals:
        setattr(module, "redis_client", original)
