"""HTTP-level tests: auth, upload-fit, sync guard, webhook, onboarding."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.main import app
from app.models import UserLifestyleProfile
from app.services import intervals_sync
from app.services.storage import LocalFitStorage, get_fit_storage
from tests.factories import profile_payload
from tests.fit_builder import build_fit, synthetic_run


@pytest.fixture
async def client(
    session: AsyncSession, storage: LocalFitStorage
) -> AsyncIterator[httpx.AsyncClient]:
    async def _session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_fit_storage] = lambda: storage
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c
    app.dependency_overrides.clear()


def _auth() -> dict[str, str]:
    return {"X-Dev-User-Id": str(uuid.uuid4())}


async def test_requires_authentication(client: httpx.AsyncClient) -> None:
    assert (await client.get("/me")).status_code == 401
    bad = await client.get("/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert bad.status_code == 401


async def test_dev_header_provisions_user(client: httpx.AsyncClient) -> None:
    headers = _auth()
    response = await client.get("/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["id"] == headers["X-Dev-User-Id"]


async def test_upload_fit_created_then_duplicate(client: httpx.AsyncClient) -> None:
    headers = _auth()
    fit = build_fit(synthetic_run(70, final_cadence_drop=6))
    files = {"file": ("lungo.fit", fit, "application/octet-stream")}

    first = await client.post("/activities/upload-fit", headers=headers, files=files)
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["created"] is True
    activity = body["activity"]
    assert activity["source"] == "MANUAL_UPLOAD"
    assert activity["name"] == "lungo"
    assert activity["computed_metrics"]["cadence_hr_divergence"]["mechanical_breakdown"] is True

    again = await client.post("/activities/upload-fit", headers=headers, files=files)
    assert again.status_code == 200
    assert again.json()["created"] is False
    assert again.json()["activity"]["id"] == activity["id"]


async def test_upload_rejects_non_fit(client: httpx.AsyncClient) -> None:
    files = {"file": ("track.gpx", b"<gpx></gpx>", "application/gpx+xml")}
    response = await client.post("/activities/upload-fit", headers=_auth(), files=files)
    assert response.status_code == 422


async def test_sync_requires_connected_intervals(client: httpx.AsyncClient) -> None:
    response = await client.post("/integrations/intervals/sync", headers=_auth())
    assert response.status_code == 409


async def test_webhook_secret_and_unknown_athlete(client: httpx.AsyncClient) -> None:
    event = {"athlete_id": "999999", "type": "ACTIVITY_UPLOADED", "activity": {}}
    bad = await client.post(
        "/integrations/intervals/webhook", json={"secret": "nope", "events": [event]}
    )
    assert bad.status_code == 401

    ok = await client.post(
        "/integrations/intervals/webhook",
        json={"secret": "test-webhook-secret", "events": [event]},
    )
    assert ok.status_code == 200
    assert ok.json() == {"accepted": 0, "ignored": 1}


async def test_onboarding_stores_encrypted_key(
    client: httpx.AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _ok(self: intervals_sync.IntervalsClient) -> dict[str, object]:
        return {"id": self.athlete_id}

    monkeypatch.setattr(intervals_sync.IntervalsClient, "get_athlete", _ok)
    headers = _auth()
    payload = {
        "display_name": "Andrea",
        "profile": profile_payload(intervals_athlete_id="i42", intervals_api_key="plain-key"),
        "personal_bests": [{"distance_m": 42195, "time_s": 11112, "achieved_on": "2026-04-12"}],
    }
    response = await client.put("/me/onboarding", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["intervals_connected"] is True
    assert "plain-key" not in response.text

    row = (
        await session.exec(
            select(UserLifestyleProfile).where(
                UserLifestyleProfile.user_id == uuid.UUID(headers["X-Dev-User-Id"])
            )
        )
    ).one()
    assert row.intervals_api_key_encrypted and row.intervals_api_key_encrypted != "plain-key"


@pytest.mark.parametrize("analyze", [True, False])
async def test_sync_backfill_skips_the_agents(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, analyze: bool
) -> None:
    from app.agents.pipeline import get_pipeline_launcher
    from app.api.v1.endpoints import integrations
    from app.schemas.ingestion import IntervalsSyncResult, SyncItem, SyncItemStatus

    async def _ok(self: intervals_sync.IntervalsClient) -> dict[str, object]:
        return {"id": self.athlete_id}

    async def _sync(
        *_: object, oldest: object, newest: object, **__: object
    ) -> IntervalsSyncResult:
        item = SyncItem(
            external_id="i1", name="Lungo", status=SyncItemStatus.IMPORTED, activity_id=uuid.uuid4()
        )
        return IntervalsSyncResult(oldest=oldest, newest=newest, items=[item])  # type: ignore[arg-type]

    launched: list[uuid.UUID] = []

    async def _launch(_user_id: uuid.UUID, activity_id: uuid.UUID) -> None:
        launched.append(activity_id)

    monkeypatch.setattr(intervals_sync.IntervalsClient, "get_athlete", _ok)
    monkeypatch.setattr(integrations, "sync_user", _sync)
    app.dependency_overrides[get_pipeline_launcher] = lambda: _launch
    headers = _auth()
    payload = {
        "profile": profile_payload(intervals_athlete_id="i42", intervals_api_key="plain-key"),
        "personal_bests": [{"distance_m": 10000, "time_s": 2400, "achieved_on": "2026-10-01"}],
    }
    assert (await client.put("/me/onboarding", headers=headers, json=payload)).status_code == 200

    response = await client.post(
        "/integrations/intervals/sync",
        headers=headers,
        json={"oldest": "2026-09-20", "analyze": analyze},
    )
    assert response.status_code == 200, response.text
    assert len(launched) == (1 if analyze else 0)
