from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.agents.context import local_today
from app.api.deps import CurrentUser, SessionDep
from app.schemas.wellness import DailyWellnessRead, WellnessCheckIn
from app.services.wellness import list_wellness, upsert_check_in

router = APIRouter(prefix="/wellness", tags=["wellness"])

EDITABLE_DAYS = 7  # a forgotten check-in can be filled in later, not rewritten months after


@router.get("", response_model=list[DailyWellnessRead])
async def read_wellness(
    user: CurrentUser,
    session: SessionDep,
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
) -> list[DailyWellnessRead]:
    today = local_today(user)
    rows = await list_wellness(session, user.id, start or today - timedelta(days=27), end or today)
    return [DailyWellnessRead.model_validate(r) for r in rows]


@router.put("/{day}", response_model=DailyWellnessRead)
async def save_check_in(
    day: date, body: WellnessCheckIn, user: CurrentUser, session: SessionDep
) -> DailyWellnessRead:
    """Morning check-in (idempotent: the athlete can change an answer)."""
    today = local_today(user)
    if not today - timedelta(days=EDITABLE_DAYS) <= day <= today:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Check-in allowed for today and the previous {EDITABLE_DAYS} days only",
        )
    return DailyWellnessRead.model_validate(await upsert_check_in(session, user.id, day, body))
