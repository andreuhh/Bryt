"""Periodic Intervals.icu poll: claims, imports and analyzes new runs right away.

Intervals.icu is never called: `sync_user` is replaced. The poll sees every connected profile
of the database, so assertions only look at the test athlete (all writes are rolled back)."""

import contextlib
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agents import scheduler
from app.models import User, UserLifestyleProfile
from app.models.enums import SurfaceSource
from app.schemas.ingestion import IntervalsSyncResult, SyncItem, SyncItemStatus
from tests.factories import profile_payload

NOW = datetime(2026, 11, 16, 10, 0, tzinfo=UTC)


async def _connected_profile(session: AsyncSession, user: User) -> UserLifestyleProfile:
    fields = profile_payload()
    profile = UserLifestyleProfile(
        user_id=user.id,
        **{
            k: v
            for k, v in fields.items()
            if k not in {"intervals_athlete_id", "intervals_api_key"}
        },
        intervals_athlete_id="i42",
        intervals_api_key_encrypted="encrypted",
    )
    session.add(profile)
    await session.commit()
    return profile


async def test_poll_imports_analyzes_and_skips_recent_syncs(
    session: AsyncSession, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _connected_profile(session, user)
    synced: list[tuple[uuid.UUID, date, date]] = []
    run_id = uuid.uuid4()

    async def _sync(
        _session: AsyncSession, *, user: User, oldest: date, newest: date, **_: object
    ) -> IntervalsSyncResult:
        synced.append((user.id, oldest, newest))
        item = SyncItem(external_id="i1", status=SyncItemStatus.IMPORTED, activity_id=run_id)
        return IntervalsSyncResult(oldest=oldest, newest=newest, items=[item])

    launched: list[tuple[uuid.UUID, uuid.UUID]] = []

    async def _launch(user_id: uuid.UUID, activity_id: uuid.UUID, *, claimed: bool = False) -> None:
        launched.append((user_id, activity_id))

    @contextlib.asynccontextmanager
    async def _factory() -> AsyncIterator[AsyncSession]:
        yield session

    monkeypatch.setattr(scheduler, "sync_user", _sync)
    await scheduler.run_intervals_poll(NOW, _launch, _factory)  # type: ignore[arg-type]
    mine = [s for s in synced if s[0] == user.id]
    assert mine == [(user.id, date(2026, 11, 14), date(2026, 11, 16))]  # 2-day window
    assert (user.id, run_id) in launched  # analyzed right away

    # Five minutes later (e.g. after the app synced on open): nothing to do for this athlete
    await scheduler.run_intervals_poll(NOW + timedelta(minutes=5), _launch, _factory)  # type: ignore[arg-type]
    assert len([s for s in synced if s[0] == user.id]) == 1


async def test_default_run_surface_fills_generic_runs_only(
    session: AsyncSession, user: User
) -> None:
    from app.models import Activity
    from app.models.enums import ActivitySource, Surface
    from app.services.profile import apply_default_run_surface

    def _run(surface: Surface | None, source: SurfaceSource | None, hour: int) -> Activity:
        return Activity(
            user_id=user.id,
            source=ActivitySource.MANUAL_UPLOAD,
            start_time=datetime(2026, 11, 10, hour, tzinfo=UTC),
            duration_s=3000,
            distance_m=10000,
            surface=surface,
            surface_source=source,
        )

    generic = _run(None, None, 6)
    trail = _run(Surface.TRAIL, SurfaceSource.DEVICE, 8)
    tagged = _run(Surface.ASPHALT, SurfaceSource.USER, 10)
    session.add_all([generic, trail, tagged])
    await session.commit()

    await apply_default_run_surface(session, user.id, Surface.MIXED)
    await session.commit()
    for a in (generic, trail, tagged):
        await session.refresh(a)
    assert (generic.surface, generic.surface_source) == (
        Surface.MIXED,
        SurfaceSource.PROFILE_DEFAULT,
    )
    assert (trail.surface, trail.surface_source) == (Surface.TRAIL, SurfaceSource.DEVICE)
    assert (tagged.surface, tagged.surface_source) == (Surface.ASPHALT, SurfaceSource.USER)
