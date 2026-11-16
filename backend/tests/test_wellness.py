"""Morning check-in: API, tenant isolation and the deterministic summary for the agents."""

import uuid
from collections.abc import AsyncIterator
from datetime import date, timedelta

import httpx
import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agents.context import local_today
from app.core.database import get_session
from app.main import app
from app.models import DailyWellness, User
from app.services.wellness import wellness_summary


@pytest.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async def _session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = _session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c
    app.dependency_overrides.clear()


def _h(user_id: uuid.UUID) -> dict[str, str]:
    return {"X-Dev-User-Id": str(user_id)}


async def test_check_in_upsert_and_isolation(client: httpx.AsyncClient, user: User) -> None:
    today = local_today(user)
    first = await client.put(f"/wellness/{today}", headers=_h(user.id), json={"sleep_hours": 7})
    assert first.status_code == 200, first.text
    # Second tap: same row, both answers
    second = await client.put(
        f"/wellness/{today}", headers=_h(user.id), json={"sleep_hours": 7, "feeling": 4}
    )
    assert second.json()["id"] == first.json()["id"] and second.json()["feeling"] == 4

    rows = (await client.get("/wellness", headers=_h(user.id))).json()
    assert [(r["day"], r["sleep_hours"], r["feeling"]) for r in rows] == [(str(today), 7.0, 4)]
    assert (await client.get("/wellness", headers=_h(uuid.uuid4()))).json() == []


@pytest.mark.parametrize("offset", [1, -8])
async def test_check_in_only_for_recent_days(
    client: httpx.AsyncClient, user: User, offset: int
) -> None:
    day = local_today(user) + timedelta(days=offset)
    response = await client.put(f"/wellness/{day}", headers=_h(user.id), json={"feeling": 3})
    assert response.status_code == 422


async def test_summary_compares_last_week_with_own_average(
    session: AsyncSession, user: User
) -> None:
    day = date(2026, 11, 16)
    for back in range(35):  # usual 8 h, last 7 days 6 h; one skipped day stays unknown
        if back == 3:
            continue
        sleep = 6.0 if back < 7 else 8.0
        session.add(
            DailyWellness(user_id=user.id, day=day - timedelta(days=back), sleep_hours=sleep)
        )
    session.add(DailyWellness(user_id=user.id, day=day - timedelta(days=40), sleep_hours=3))
    await session.commit()

    summary = await wellness_summary(session, user.id, day)
    assert summary.check_in is not None and summary.check_in.sleep_hours == 6
    assert summary.last_7d.days_logged == 6 and summary.last_7d.avg_sleep_hours == 6
    assert summary.previous_28d.days_logged == 28 and summary.previous_28d.avg_sleep_hours == 8
    assert summary.last_7d.avg_feeling is None
