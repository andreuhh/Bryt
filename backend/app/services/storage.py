"""Storage of original .fit files. Local filesystem now; swap for Supabase Storage later."""

import asyncio
import uuid
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings


class FitStorage(Protocol):
    async def save(self, user_id: uuid.UUID, sha256: str, data: bytes) -> str: ...


class LocalFitStorage:
    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)

    async def save(self, user_id: uuid.UUID, sha256: str, data: bytes) -> str:
        """Content-addressed per tenant: fit/{user_id}/{sha256}.fit. Returns the relative path."""
        relative = Path("fit") / str(user_id) / f"{sha256}.fit"
        target = self.base_dir / relative

        def _write() -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

        await asyncio.to_thread(_write)
        return relative.as_posix()


def get_fit_storage() -> FitStorage:
    return LocalFitStorage(get_settings().storage_dir)
