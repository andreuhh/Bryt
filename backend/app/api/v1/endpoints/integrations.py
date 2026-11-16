import hmac
import logging
import uuid
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.agents.pipeline import PipelineLauncher, get_pipeline_launcher
from app.api.deps import CurrentUser, SessionDep
from app.core.config import get_settings
from app.core.database import SessionFactory
from app.models import User
from app.schemas.ingestion import (
    IntervalsSyncRequest,
    IntervalsSyncResult,
    IntervalsWebhookPayload,
    SyncItemStatus,
    WebhookAck,
)
from app.services.intervals_sync import (
    IntervalsAuthError,
    IntervalsError,
    default_window,
    find_profile_by_intervals_athlete,
    sync_user,
)
from app.services.profile import get_profile
from app.services.storage import FitStorage, get_fit_storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/intervals", tags=["integrations"])

WEBHOOK_ACTIVITY_EVENTS = {"ACTIVITY_UPLOADED", "ACTIVITY_ANALYZED"}


@router.post("/sync", response_model=IntervalsSyncResult)
async def sync_intervals(
    user: CurrentUser,
    session: SessionDep,
    background: BackgroundTasks,
    launch_pipeline: Annotated[PipelineLauncher, Depends(get_pipeline_launcher)],
    storage: Annotated[FitStorage, Depends(get_fit_storage)],
    body: IntervalsSyncRequest | None = None,
) -> IntervalsSyncResult:
    profile = await get_profile(session, user)
    if profile is None or not profile.intervals_connected:
        raise HTTPException(status.HTTP_409_CONFLICT, "Intervals.icu not connected")
    try:
        oldest, newest = default_window(
            body.oldest if body else None, body.newest if body else None
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    try:
        result = await sync_user(
            session, user=user, profile=profile, storage=storage, oldest=oldest, newest=newest
        )
    except IntervalsAuthError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except IntervalsError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    if body is None or body.analyze:
        for item in result.items:
            if item.status == SyncItemStatus.IMPORTED and item.activity_id:
                background.add_task(launch_pipeline, user.id, item.activity_id)
    return result


@router.post("/webhook", response_model=WebhookAck)
async def intervals_webhook(
    payload: IntervalsWebhookPayload,
    background: BackgroundTasks,
    session: SessionDep,
) -> WebhookAck:
    """Public endpoint called by Intervals.icu (requires a registered Intervals.icu app).

    Authenticated by the shared `secret` in the payload. Always answers fast with 2xx;
    the actual download runs in background (Intervals retries on non-2xx).
    """
    expected = get_settings().intervals_webhook_secret
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Webhook not configured")
    if not hmac.compare_digest(payload.secret.encode(), expected.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook secret")

    accepted = ignored = 0
    for event in payload.events:
        profile = (
            await find_profile_by_intervals_athlete(session, event.athlete_id)
            if event.type in WEBHOOK_ACTIVITY_EVENTS
            else None
        )
        if profile is None:
            ignored += 1
            continue
        day = _event_day(event.activity)
        background.add_task(_sync_user_window, profile.user_id, day - timedelta(days=1), day)
        accepted += 1
    return WebhookAck(accepted=accepted, ignored=ignored)


def _event_day(activity: dict[str, object] | None) -> date:
    raw = (activity or {}).get("start_date_local")
    if isinstance(raw, str):
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            pass
    return date.today()


async def _sync_user_window(user_id: uuid.UUID, oldest: date, newest: date) -> None:
    """Background job: own DB session, never raises (logs instead)."""
    async with SessionFactory() as session:
        user = await session.get(User, user_id)
        profile = await get_profile(session, user) if user else None
        if user is None or profile is None or not profile.intervals_connected:
            return
        try:
            result = await sync_user(
                session,
                user=user,
                profile=profile,
                storage=get_fit_storage(),
                oldest=oldest,
                newest=newest,
            )
            logger.info("Webhook sync user=%s items=%d", user_id, len(result.items))
        except IntervalsError:
            logger.exception("Webhook sync failed for user=%s", user_id)
            return

    launch_pipeline = get_pipeline_launcher()
    for item in result.items:
        if item.status == SyncItemStatus.IMPORTED and item.activity_id:
            await launch_pipeline(user_id, item.activity_id)
