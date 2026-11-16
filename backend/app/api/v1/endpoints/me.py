from fastapi import APIRouter, HTTPException, status

from app.agents.context import MissingProfileError, athlete_context, local_today
from app.api.deps import CurrentUser, SessionDep
from app.schemas.training import AthleteCalibration
from app.schemas.user import (
    OnboardingPayload,
    PersonalBestRead,
    ProfileRead,
    ProfileUpdate,
    UserRead,
)
from app.services.intervals_sync import IntervalsAuthError, IntervalsClient, IntervalsError
from app.services.profile import (
    get_profile,
    list_personal_bests,
    save_onboarding,
    update_profile,
)

router = APIRouter(tags=["me"])


@router.get("/me", response_model=UserRead)
async def read_me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.get("/me/profile", response_model=ProfileRead)
async def read_profile(user: CurrentUser, session: SessionDep) -> ProfileRead:
    profile = await get_profile(session, user)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Onboarding not completed")
    return ProfileRead.model_validate(profile)


@router.get("/me/personal-bests", response_model=list[PersonalBestRead])
async def read_personal_bests(user: CurrentUser, session: SessionDep) -> list[PersonalBestRead]:
    """Most recent first. Includes non-PB race results (event_name) used as context."""
    return [PersonalBestRead.model_validate(pb) for pb in await list_personal_bests(session, user)]


@router.get("/me/calibration", response_model=AthleteCalibration)
async def read_calibration(user: CurrentUser, session: SessionDep) -> AthleteCalibration:
    """Threshold pace/HR and training zones, recomputed from the current profile and PBs."""
    try:
        _, calibration = await athlete_context(session, user, local_today(user))
    except MissingProfileError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Onboarding not completed") from exc
    return calibration


@router.put("/me/onboarding", response_model=ProfileRead)
async def submit_onboarding(
    payload: OnboardingPayload, user: CurrentUser, session: SessionDep
) -> ProfileRead:
    """Saves the wizard. Intervals.icu credentials are verified live before being stored."""
    athlete_id, api_key = payload.profile.intervals_athlete_id, payload.profile.intervals_api_key
    if athlete_id and api_key:
        try:
            async with IntervalsClient(athlete_id, api_key.get_secret_value()) as client:
                await client.get_athlete()
        except IntervalsAuthError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except IntervalsError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    profile = await save_onboarding(session, user, payload)
    return ProfileRead.model_validate(profile)


@router.patch("/me/profile", response_model=ProfileRead)
async def patch_profile(
    changes: ProfileUpdate, user: CurrentUser, session: SessionDep
) -> ProfileRead:
    """Settings page: partial profile update. Zones are recomputed on the next read."""
    profile = await get_profile(session, user)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Onboarding not completed")
    athlete_id = changes.intervals_athlete_id or profile.intervals_athlete_id
    if changes.intervals_api_key is not None:
        if not athlete_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "intervals_athlete_id required"
            )
        try:
            async with IntervalsClient(
                athlete_id, changes.intervals_api_key.get_secret_value()
            ) as c:
                await c.get_athlete()
        except IntervalsAuthError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except IntervalsError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return ProfileRead.model_validate(await update_profile(session, profile, changes))
