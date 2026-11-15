"""Intervals.icu connector (personal API key, zero cost).

Auth: HTTP Basic, username literal "API_KEY", password = athlete's personal key.
Files: GET /activity/{id}/file returns the ORIGINAL upload (gzip; fit/gpx/tcx). When the
original is not a FIT we fall back to /activity/{id}/fit-file (Intervals-generated FIT).
Strava-sourced activities expose no file via the API (Strava ToS) → reported as NO_FILE.
"""

from datetime import date, timedelta
from types import TracebackType
from typing import Self

import httpx
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.security import decrypt_secret
from app.models import Activity, User, UserLifestyleProfile
from app.models.enums import ActivitySource
from app.schemas.ingestion import (
    IntervalsActivity,
    IntervalsSyncResult,
    SyncItem,
    SyncItemStatus,
)
from app.services.fit_files import InvalidFitFileError, extract_fit_bytes
from app.services.fit_parser import FitParseError, UnsupportedSportError
from app.services.ingestion import ingest_fit
from app.services.storage import FitStorage

RUNNING_TYPES = {"Run", "TrailRun", "VirtualRun"}


class IntervalsError(Exception):
    pass


class IntervalsAuthError(IntervalsError):
    pass


class IntervalsFileUnavailableError(IntervalsError):
    pass


class IntervalsClient:
    def __init__(
        self,
        athlete_id: str,
        api_key: str,
        *,
        base_url: str | None = None,
        timeout_s: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        settings = get_settings()
        self.athlete_id = athlete_id
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.intervals_base_url,
            auth=httpx.BasicAuth("API_KEY", api_key),
            timeout=timeout_s or settings.intervals_timeout_s,
            transport=transport,
            headers={"Accept": "application/json"},
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    async def _get(self, path: str, **params: str) -> httpx.Response:
        try:
            response = await self._client.get(path, params=params or None)
        except httpx.HTTPError as exc:
            raise IntervalsError(f"Intervals.icu unreachable: {exc}") from exc
        if response.status_code in (401, 403):
            raise IntervalsAuthError("Intervals.icu rejected the Athlete ID / API Key")
        return response

    async def get_athlete(self) -> dict[str, object]:
        """Cheap call used to validate credentials at connection time."""
        response = await self._get(f"/athlete/{self.athlete_id}")
        if response.status_code == 404:
            raise IntervalsAuthError("Athlete not found on Intervals.icu")
        response.raise_for_status()
        data: dict[str, object] = response.json()
        return data

    async def list_activities(self, oldest: date, newest: date) -> list[IntervalsActivity]:
        response = await self._get(
            f"/athlete/{self.athlete_id}/activities",
            oldest=oldest.isoformat(),
            newest=newest.isoformat(),
        )
        response.raise_for_status()
        return [IntervalsActivity.model_validate(item) for item in response.json()]

    async def download_fit(self, activity: IntervalsActivity, max_bytes: int) -> bytes:
        path = "file" if (activity.file_type or "").lower() == "fit" else "fit-file"
        response = await self._get(f"/activity/{activity.id}/{path}")
        if response.status_code in (404, 422) or not response.content:
            raise IntervalsFileUnavailableError("No file available for this activity")
        response.raise_for_status()
        return extract_fit_bytes(response.content, max_bytes)


def client_for(profile: UserLifestyleProfile) -> IntervalsClient:
    if not profile.intervals_athlete_id or not profile.intervals_api_key_encrypted:
        raise IntervalsAuthError("Intervals.icu not connected")
    return IntervalsClient(
        profile.intervals_athlete_id, decrypt_secret(profile.intervals_api_key_encrypted)
    )


def default_window(oldest: date | None, newest: date | None) -> tuple[date, date]:
    newest = newest or date.today()
    oldest = oldest or newest - timedelta(days=get_settings().intervals_sync_default_days)
    if oldest > newest:
        raise ValueError("oldest must be <= newest")
    return oldest, newest


async def sync_intervals_activities(
    session: AsyncSession,
    *,
    user: User,
    client: IntervalsClient,
    storage: FitStorage,
    oldest: date,
    newest: date,
) -> IntervalsSyncResult:
    """Downloads and ingests new running activities in [oldest, newest]. Idempotent."""
    max_bytes = get_settings().max_fit_upload_mb * 1024 * 1024
    remote = await client.list_activities(oldest, newest)

    known_stmt = select(Activity.external_id, Activity.id).where(
        Activity.user_id == user.id,
        Activity.source == ActivitySource.INTERVALS,
        col(Activity.external_id).in_([a.id for a in remote]),
    )
    known = {ext: act_id for ext, act_id in (await session.exec(known_stmt)).all()}

    items: list[SyncItem] = []
    for act in remote:
        item = SyncItem(
            external_id=act.id, name=act.name, sport=act.type, status=SyncItemStatus.FAILED
        )
        if act.id in known:
            item.status, item.activity_id = SyncItemStatus.ALREADY_PRESENT, known[act.id]
        elif act.type not in RUNNING_TYPES:
            item.status = SyncItemStatus.UNSUPPORTED_SPORT
        elif (act.source or "").upper() == "STRAVA":
            item.status = SyncItemStatus.NO_FILE
            item.detail = "Strava activities are not available via the Intervals.icu API"
        else:
            try:
                fit_bytes = await client.download_fit(act, max_bytes)
                result = await ingest_fit(
                    session,
                    user=user,
                    fit_bytes=fit_bytes,
                    source=ActivitySource.INTERVALS,
                    storage=storage,
                    external_id=act.id,
                    name=act.name,
                )
                item.activity_id = result.activity.id
                item.status = (
                    SyncItemStatus.IMPORTED if result.created else SyncItemStatus.ALREADY_PRESENT
                )
            except IntervalsAuthError:
                raise
            except IntervalsFileUnavailableError as exc:
                item.status, item.detail = SyncItemStatus.NO_FILE, str(exc)
            except UnsupportedSportError as exc:
                item.status, item.detail = SyncItemStatus.UNSUPPORTED_SPORT, str(exc)
            except (IntervalsError, InvalidFitFileError, FitParseError, httpx.HTTPError) as exc:
                item.detail = str(exc)
        items.append(item)

    return IntervalsSyncResult(oldest=oldest, newest=newest, items=items)


async def find_profile_by_intervals_athlete(
    session: AsyncSession, athlete_id: str
) -> UserLifestyleProfile | None:
    """Webhook athlete ids may come with or without the 'i' prefix."""
    bare = athlete_id.removeprefix("i")
    stmt = select(UserLifestyleProfile).where(
        col(UserLifestyleProfile.intervals_athlete_id).in_([bare, f"i{bare}"])
    )
    return (await session.exec(stmt)).first()
