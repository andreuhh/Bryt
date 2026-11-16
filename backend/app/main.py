import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.scheduler import intervals_poll_loop, scheduler_loop
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.security import check_encryption_key


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    check_encryption_key()
    settings = get_settings()
    tasks = []
    if settings.scheduler_enabled:
        tasks.append(asyncio.create_task(scheduler_loop()))
    if settings.intervals_poll_enabled:
        tasks.append(asyncio.create_task(intervals_poll_loop()))
    yield
    for task in tasks:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=f"{settings.app_name} API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
