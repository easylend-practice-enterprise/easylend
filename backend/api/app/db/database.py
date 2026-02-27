from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,  # Zet op True om SQL in de terminal te zien
    future=True,
)

# 2. De Sessie Fabriek
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


# 3. Dependency voor FastAPI
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
