"""Deterministic training history and data-quality checks used as agent context."""

import math
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Activity, ActivityStream, PersonalBest, Workout
from app.models.enums import DataCoverage, WorkoutStatus, WorkoutType
from app.schemas.context import ElevationQuality, RecentRace, TrainingBaseline
from app.services.fit_parser import elevation_gain_loss

BASELINE_DAYS = 28
# Coverage is judged on a longer window: a taper, a race and its recovery can halve the last
# 4 weeks of a complete recording, which is real low volume, not missing data.
HABITUAL_DAYS = 56
MIN_ACTIVITIES_FOR_COVERAGE = 8
MIN_DECLARED_RATIO = 0.5  # recorded km below half of the declared volume → LOW coverage
RACE_LOOKBACK_DAYS = 28
RECOVERY_M_PER_DAY = 1609.344  # coaching rule of thumb: one easy day per mile raced


async def training_baseline(
    session: AsyncSession,
    user_id: uuid.UUID,
    before: datetime,
    exclude_activity_id: uuid.UUID | None = None,
    declared_weekly_km: float | None = None,
) -> TrainingBaseline:
    """28-day history, with data coverage judged over 8 weeks. With sparse recordings (new
    user, no Intervals sync yet) the declared weekly volume is the reference and the
    acute:chronic ratio is withheld (meaningless)."""
    since = before - timedelta(days=HABITUAL_DAYS)
    stmt = select(Activity).where(
        Activity.user_id == user_id,
        col(Activity.start_time) >= since,
        col(Activity.start_time) < before,
    )
    if exclude_activity_id is not None:
        stmt = stmt.where(Activity.id != exclude_activity_id)
    habitual_acts = list((await session.exec(stmt)).all())
    acts = [a for a in habitual_acts if a.start_time >= before - timedelta(days=BASELINE_DAYS)]

    total_km = sum(a.distance_m for a in acts) / 1000
    acute_km = sum(a.distance_m for a in acts if a.start_time >= before - timedelta(days=7)) / 1000
    chronic_weekly = total_km / (BASELINE_DAYS / 7)
    habitual_weekly = sum(a.distance_m for a in habitual_acts) / 1000 / (HABITUAL_DAYS / 7)
    weekly_km = [0.0] * (HABITUAL_DAYS // 7)
    for a in habitual_acts:
        weekly_km[min(int((a.start_time - since).days // 7), len(weekly_km) - 1)] += (
            a.distance_m / 1000
        )
    paced = [a for a in acts if a.avg_pace_s_per_km and a.distance_m > 0]
    paced_km = sum(a.distance_m for a in paced) / 1000
    cadenced = [a for a in acts if a.avg_cadence_spm]

    by_surface: dict[str, float] = defaultdict(float)
    for a in acts:
        by_surface[a.surface.value if a.surface else "UNKNOWN"] += a.distance_m / 1000

    sparse = len(habitual_acts) < MIN_ACTIVITIES_FOR_COVERAGE or (
        declared_weekly_km is not None and habitual_weekly < MIN_DECLARED_RATIO * declared_weekly_km
    )
    coverage = DataCoverage.LOW if sparse else DataCoverage.HIGH
    effective = declared_weekly_km if sparse and declared_weekly_km else chronic_weekly
    races = await recent_races(session, user_id, before, exclude_activity_id)

    return TrainingBaseline(
        window_days=BASELINE_DAYS,
        data_coverage=coverage,
        declared_weekly_km=declared_weekly_km,
        effective_weekly_km=round(effective, 1),
        habitual_window_days=HABITUAL_DAYS,
        habitual_weekly_km=round(habitual_weekly, 1),
        weekly_km=[round(km, 1) for km in weekly_km],
        recent_races=races,
        in_post_race_recovery=any(r.recovery_until >= before.date() for r in races),
        activities=len(acts),
        total_km=round(total_km, 1),
        weekly_avg_km=round(chronic_weekly, 1),
        acute_7d_km=round(acute_km, 1),
        acute_chronic_ratio=round(acute_km / chronic_weekly, 2)
        if chronic_weekly and not sparse
        else None,
        avg_pace_s_per_km=round(
            sum((a.avg_pace_s_per_km or 0) * a.distance_m / 1000 for a in paced) / paced_km, 1
        )
        if paced_km
        else None,
        fastest_avg_pace_s_per_km=min((a.avg_pace_s_per_km or 0) for a in paced) if paced else None,
        avg_cadence_spm=round(sum(a.avg_cadence_spm or 0 for a in cadenced) / len(cadenced), 1)
        if cadenced
        else None,
        longest_run_km=round(max(a.distance_m for a in acts) / 1000, 1) if acts else None,
        total_elevation_loss_m=round(sum(a.elevation_loss_m or 0 for a in acts), 0)
        if acts
        else None,
        km_by_surface={k: round(v, 1) for k, v in sorted(by_surface.items())},
    )


async def recent_races(
    session: AsyncSession,
    user_id: uuid.UUID,
    before: datetime,
    exclude_activity_id: uuid.UUID | None = None,
) -> list[RecentRace]:
    """Races of the last 4 weeks: results the athlete logged (PB table, which also keeps
    non-PB races) and completed RACE workouts of the plan. One entry per day."""
    today = before.date()
    since = today - timedelta(days=RACE_LOOKBACK_DAYS)
    found: dict[date, RecentRace] = {}

    def add(day: date, distance_m: int, name: str | None) -> None:
        if since <= day < today and day not in found:
            found[day] = RecentRace(
                date=day,
                days_ago=(today - day).days,
                distance_m=distance_m,
                name=name,
                recovery_until=day + timedelta(days=math.ceil(distance_m / RECOVERY_M_PER_DAY)),
            )

    raced = (
        await session.exec(
            select(Workout, Activity)
            .join(Activity, col(Activity.id) == col(Workout.activity_id))
            .where(
                Workout.user_id == user_id,
                Workout.workout_type == WorkoutType.RACE,
                Workout.status == WorkoutStatus.COMPLETED,
                col(Workout.scheduled_date) >= since,
            )
        )
    ).all()
    for workout, activity in raced:
        if activity.id != exclude_activity_id:
            add(workout.scheduled_date, round(activity.distance_m), activity.name or workout.title)
    logged = (
        await session.exec(
            select(PersonalBest).where(
                PersonalBest.user_id == user_id, col(PersonalBest.achieved_on) >= since
            )
        )
    ).all()
    for pb in logged:
        add(pb.achieved_on, pb.distance_m, pb.event_name)
    return sorted(found.values(), key=lambda r: r.date)


def elevation_quality(activity: Activity, stream: ActivityStream | None) -> ElevationQuality:
    """Flags device elevation that cannot be trusted for eccentric-load estimates.

    The totals declared by the device must agree with gain/loss recomputed from the recorded
    altitude series. GPS-only altitude (no barometer) typically fails this: the series wanders
    by tens of metres on flat courses while the declared totals say something else.
    """
    gain, loss = activity.elevation_gain_m, activity.elevation_loss_m
    alts = [x for x in (stream.elevation_m if stream else []) if x is not None]
    if gain is None or loss is None or len(alts) < 10:
        return ElevationQuality(reliable=None, reason="dati di altitudine assenti o insufficienti")

    rec_gain, rec_loss = elevation_gain_loss(alts)
    assert rec_gain is not None and rec_loss is not None
    mismatch = abs(gain - rec_gain) + abs(loss - rec_loss)
    tolerance = max(10.0, 0.5 * (rec_gain + rec_loss))
    if mismatch > tolerance:
        return ElevationQuality(
            reliable=False,
            reason=(
                f"dislivello dichiarato dal dispositivo (+{gain:.0f}/-{loss:.0f} m) incoerente "
                f"con la quota registrata (+{rec_gain:.0f}/-{rec_loss:.0f} m, escursione "
                f"{max(alts) - min(alts):.0f} m): probabile altitudine da GPS, non usarla per "
                "stimare il carico eccentrico"
            ),
        )
    return ElevationQuality(reliable=True, reason="dislivello coerente con la quota registrata")
