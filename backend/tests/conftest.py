"""Test configuration. Env overrides are applied BEFORE the app is imported (settings cache)."""

import os

from cryptography.fernet import Fernet

os.environ["ENVIRONMENT"] = "development"
os.environ["INTERVALS_WEBHOOK_SECRET"] = "test-webhook-secret"
os.environ["AGENTS_ENABLED"] = "false"  # tests override the pipeline launcher explicitly
if not os.environ.get("ENCRYPTION_KEY"):
    os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()

import uuid  # noqa: E402
from collections.abc import AsyncIterator  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlmodel.ext.asyncio.session import AsyncSession  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.models import User  # noqa: E402
from app.services.storage import LocalFitStorage  # noqa: E402

get_settings.cache_clear()


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Real PostgreSQL session wrapped in a rolled-back transaction (commits → savepoints)."""
    engine = create_async_engine(get_settings().database_url)
    try:
        conn = await engine.connect()
    except OSError:
        await engine.dispose()
        pytest.skip("PostgreSQL not reachable (docker compose up -d db)")
    trans = await conn.begin()
    async with AsyncSession(
        bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
    ) as s:
        yield s
    await trans.rollback()
    await conn.close()
    await engine.dispose()


@pytest.fixture
def storage(tmp_path: Path) -> LocalFitStorage:
    return LocalFitStorage(tmp_path)


@pytest.fixture
async def user(session: AsyncSession) -> User:
    u = User(id=uuid.uuid4(), email=f"{uuid.uuid4().hex[:8]}@bryt.test", timezone="Europe/Rome")
    session.add(u)
    await session.commit()
    return u
