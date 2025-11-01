from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from .config import settings


class Base(DeclarativeBase):
    pass


engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,  # psycopg3 supports async with AsyncEngine
    pool_pre_ping=True,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def lifespan_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def ensure_extensions() -> None:
    # Import models here to avoid circular imports at module load time
    from .models import Base as ModelsBase

    async with engine.begin() as conn:
        # Ensure default schema and extension
        await conn.execute(text("SET search_path TO public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    # Create tables with a sync engine handle to be safe
    await engine.run_sync(lambda sync_engine: ModelsBase.metadata.create_all(sync_engine))
    # Create IVFFlat index (safe if already exists)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_article_embeddings_vec "
                    "ON article_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
                )
            )
    except Exception:
        # IVFFlat requires data; creation can be deferred
        pass


