"""Persist the onboarding wizard: user details, lifestyle profile, personal bests."""

import uuid

from sqlalchemy import or_, update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import encrypt_secret
from app.models import Activity, PersonalBest, User, UserLifestyleProfile
from app.models.enums import Surface, SurfaceSource
from app.schemas.user import OnboardingPayload, ProfileUpdate


async def apply_default_run_surface(
    session: AsyncSession, user_id: uuid.UUID, surface: Surface | None
) -> None:
    """Generic runs without a surface (or with the previous default) follow the athlete's new
    usual surface; surfaces tagged by the athlete or recorded by the watch are never touched."""
    await session.exec(
        update(Activity)
        .where(
            col(Activity.user_id) == user_id,
            or_(
                col(Activity.surface_source).is_(None),
                col(Activity.surface_source) == SurfaceSource.PROFILE_DEFAULT,
            ),
        )
        .values(surface=surface, surface_source=SurfaceSource.PROFILE_DEFAULT if surface else None)
    )


async def get_profile(session: AsyncSession, user: User) -> UserLifestyleProfile | None:
    stmt = select(UserLifestyleProfile).where(UserLifestyleProfile.user_id == user.id)
    return (await session.exec(stmt)).first()


async def save_onboarding(
    session: AsyncSession, user: User, payload: OnboardingPayload
) -> UserLifestyleProfile:
    """Upsert the profile (re-running the wizard updates it) and append the given PBs.

    Intervals.icu credentials must already be validated by the caller. The API key is
    write-only (never sent back to the client), so a re-run without credentials keeps the
    stored ones: disconnecting is an explicit settings action, not a side effect.
    """
    user.display_name = payload.display_name or user.display_name
    user.timezone = payload.timezone
    user.onboarding_completed = True
    session.add(user)

    fields = payload.profile.model_dump(exclude={"intervals_api_key", "intervals_athlete_id"})
    profile = await get_profile(session, user)
    if profile is None:
        profile = UserLifestyleProfile(user_id=user.id, **fields)
    else:
        for key, value in fields.items():
            setattr(profile, key, value)

    api_key = payload.profile.intervals_api_key
    if api_key is not None:  # the schema guarantees athlete id and key come together
        profile.intervals_athlete_id = payload.profile.intervals_athlete_id
        profile.intervals_api_key_encrypted = encrypt_secret(api_key.get_secret_value())
    session.add(profile)
    await apply_default_run_surface(session, user.id, profile.default_run_surface)

    existing = {
        (pb.distance_m, pb.time_s, pb.achieved_on)
        for pb in (
            await session.exec(select(PersonalBest).where(PersonalBest.user_id == user.id))
        ).all()
    }
    for pb in payload.personal_bests:  # re-running the wizard must not duplicate PBs
        if (pb.distance_m, pb.time_s, pb.achieved_on) not in existing:
            session.add(PersonalBest(user_id=user.id, **pb.model_dump()))

    await session.commit()
    await session.refresh(profile)
    return profile


async def update_profile(
    session: AsyncSession, profile: UserLifestyleProfile, changes: ProfileUpdate
) -> UserLifestyleProfile:
    """Partial update (only fields explicitly sent). Credentials validated by the caller."""
    data = changes.model_dump(exclude_unset=True, exclude={"intervals_api_key"})
    for key, value in data.items():
        setattr(profile, key, value)
    if changes.intervals_api_key is not None:
        profile.intervals_api_key_encrypted = encrypt_secret(
            changes.intervals_api_key.get_secret_value()
        )
    session.add(profile)
    if "default_run_surface" in data:
        await apply_default_run_surface(session, profile.user_id, profile.default_run_surface)
    await session.commit()
    await session.refresh(profile)
    return profile


async def list_personal_bests(session: AsyncSession, user: User) -> list[PersonalBest]:
    stmt = (
        select(PersonalBest)
        .where(PersonalBest.user_id == user.id)
        .order_by(col(PersonalBest.achieved_on).desc())
    )
    return list((await session.exec(stmt)).all())
