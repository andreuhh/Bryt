"""Async SQLModel engine and session dependency (PostgreSQL shared state)."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings

engine: AsyncEngine = create_async_engine(get_settings().database_url, pool_pre_ping=True)

SessionFactory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session
