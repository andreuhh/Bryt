from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.user import OnboardingPayload, ProfileRead, UserRead
from app.services.intervals_sync import IntervalsAuthError, IntervalsClient, IntervalsError
from app.services.profile import get_profile, save_onboarding

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
