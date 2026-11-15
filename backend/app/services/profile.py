"""Persist the onboarding wizard: user details, lifestyle profile, personal bests."""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import encrypt_secret
from app.models import PersonalBest, User, UserLifestyleProfile
from app.schemas.user import OnboardingPayload


async def get_profile(session: AsyncSession, user: User) -> UserLifestyleProfile | None:
    stmt = select(UserLifestyleProfile).where(UserLifestyleProfile.user_id == user.id)
    return (await session.exec(stmt)).first()


async def save_onboarding(
    session: AsyncSession, user: User, payload: OnboardingPayload
) -> UserLifestyleProfile:
    """Upsert the profile (re-running the wizard updates it) and append the given PBs.

    Intervals.icu credentials must already be validated by the caller.
    """
    user.display_name = payload.display_name or user.display_name
    user.timezone = payload.timezone
    user.onboarding_completed = True
    session.add(user)

    fields = payload.profile.model_dump(exclude={"intervals_api_key"})
    profile = await get_profile(session, user)
    if profile is None:
        profile = UserLifestyleProfile(user_id=user.id, **fields)
    else:
        for key, value in fields.items():
            setattr(profile, key, value)

    api_key = payload.profile.intervals_api_key
    profile.intervals_api_key_encrypted = (
        encrypt_secret(api_key.get_secret_value()) if api_key else None
    )
    session.add(profile)

    for pb in payload.personal_bests:
        session.add(PersonalBest(user_id=user.id, **pb.model_dump()))

    await session.commit()
    await session.refresh(profile)
    return profile
