from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text, event
from pgvector.psycopg import register_vector

from .config import settings


class Base(DeclarativeBase):
    pass


engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,  # psycopg3 supports async with AsyncEngine
    pool_pre_ping=True,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


# Ensure pgvector types are registered with psycopg (needed for binding params as vector)
@event.listens_for(engine.sync_engine, "connect")
def _register_pgvector(dbapi_connection, _record) -> None:  # type: ignore[no-redef]
    try:
        register_vector(dbapi_connection)
    except Exception:
        # ignore if already registered or not available
        pass


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
    # Create tables using connection.run_sync (async-safe in SQLAlchemy 2.x)
    async with engine.begin() as conn:
        await conn.run_sync(ModelsBase.metadata.create_all)
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


