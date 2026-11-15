"""Intervals.icu sync against a mocked HTTP API + real PostgreSQL."""

import base64
import gzip
from datetime import UTC, date, datetime

import httpx
import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Activity, ActivityStream, TrainingPlan, User, Workout
from app.models.enums import Methodology, PlanStatus, SessionSlot, WorkoutStatus, WorkoutType
from app.schemas.ingestion import SyncItemStatus
from app.services.intervals_sync import (
    IntervalsAuthError,
    IntervalsClient,
    sync_intervals_activities,
)
from app.services.storage import LocalFitStorage
from tests.fit_builder import build_fit, synthetic_run

API_KEY = "user-personal-key"
START = datetime(2026, 11, 10, 6, 30, tzinfo=UTC)  # 07:30 Europe/Rome
FIT = build_fit(synthetic_run(40), start=START)
FIT_GENERATED = build_fit(synthetic_run(30, seed=3), start=START)

REMOTE = [
    {"id": "i1001", "name": "Lungo", "type": "Run", "file_type": "fit", "source": "GARMIN_CONNECT"},
    {"id": "i1002", "name": "Bici", "type": "Ride", "file_type": "fit"},
    {"id": "i1003", "name": "Da Strava", "type": "Run", "source": "STRAVA"},
    {"id": "i1004", "name": "Treadmill GPX", "type": "VirtualRun", "file_type": "gpx"},
]


def _handler(request: httpx.Request) -> httpx.Response:
    expected = "Basic " + base64.b64encode(f"API_KEY:{API_KEY}".encode()).decode()
    if request.headers.get("authorization") != expected:
        return httpx.Response(401)
    path = request.url.path
    if path == "/api/v1/athlete/i42/activities":
        assert request.url.params["oldest"] == "2026-11-01"
        return httpx.Response(200, json=REMOTE)
    if path == "/api/v1/activity/i1001/file":
        return httpx.Response(200, content=gzip.compress(FIT))
    if path == "/api/v1/activity/i1004/fit-file":  # original is GPX → generated FIT
        return httpx.Response(200, content=gzip.compress(FIT_GENERATED))
    return httpx.Response(404)


def _client(api_key: str = API_KEY) -> IntervalsClient:
    return IntervalsClient(
        "i42",
        api_key,
        base_url="https://intervals.test/api/v1",
        transport=httpx.MockTransport(_handler),
    )


async def _sync(
    session: AsyncSession, user: User, storage: LocalFitStorage, api_key: str = API_KEY
):  # type: ignore[no-untyped-def]
    async with _client(api_key) as client:
        return await sync_intervals_activities(
            session,
            user=user,
            client=client,
            storage=storage,
            oldest=date(2026, 11, 1),
            newest=date(2026, 11, 15),
        )


async def test_sync_imports_running_and_reports_the_rest(
    session: AsyncSession, user: User, storage: LocalFitStorage
) -> None:
    result = await _sync(session, user, storage)
    status = {item.external_id: item.status for item in result.items}
    assert status == {
        "i1001": SyncItemStatus.IMPORTED,
        "i1002": SyncItemStatus.UNSUPPORTED_SPORT,
        "i1003": SyncItemStatus.NO_FILE,
        "i1004": SyncItemStatus.IMPORTED,
    }

    activities = (await session.exec(select(Activity).where(Activity.user_id == user.id))).all()
    assert {a.external_id for a in activities} == {"i1001", "i1004"}
    lungo = next(a for a in activities if a.external_id == "i1001")
    assert lungo.name == "Lungo"
    assert lungo.computed_metrics["cadence_hr_divergence"]["evaluated"] is True
    assert (storage.base_dir / (lungo.fit_storage_path or "")).exists()

    stream = (
        await session.exec(select(ActivityStream).where(ActivityStream.activity_id == lungo.id))
    ).one()
    assert stream.sample_count == 40 * 60


async def test_sync_is_idempotent(
    session: AsyncSession, user: User, storage: LocalFitStorage
) -> None:
    await _sync(session, user, storage)
    second = await _sync(session, user, storage)
    assert second.count(SyncItemStatus.IMPORTED) == 0
    assert second.count(SyncItemStatus.ALREADY_PRESENT) == 2


async def test_sync_links_planned_workout(
    session: AsyncSession, user: User, storage: LocalFitStorage
) -> None:
    plan = TrainingPlan(
        user_id=user.id,
        name="Test",
        status=PlanStatus.ACTIVE,
        methodology=Methodology.DOUBLE_THRESHOLD,
        start_date=date(2026, 11, 1),
        end_date=date(2026, 12, 1),
    )
    session.add(plan)
    await session.flush()
    am = Workout(
        user_id=user.id,
        plan_id=plan.id,
        scheduled_date=date(2026, 11, 10),
        session_slot=SessionSlot.AM,
        workout_type=WorkoutType.THRESHOLD,
        title="Soglia AM",
    )
    pm = Workout(
        user_id=user.id,
        plan_id=plan.id,
        scheduled_date=date(2026, 11, 10),
        session_slot=SessionSlot.PM,
        workout_type=WorkoutType.THRESHOLD,
        title="Soglia PM",
    )
    session.add_all([am, pm])
    await session.commit()

    await _sync(session, user, storage)
    await session.refresh(am)
    await session.refresh(pm)
    # Run at 07:30 local → AM session completed; the PM one gets the second run of the day
    assert am.status == WorkoutStatus.COMPLETED and am.activity_id is not None
    assert pm.status == WorkoutStatus.COMPLETED


async def test_bad_credentials_raise(
    session: AsyncSession, user: User, storage: LocalFitStorage
) -> None:
    with pytest.raises(IntervalsAuthError):
        await _sync(session, user, storage, api_key="wrong")
