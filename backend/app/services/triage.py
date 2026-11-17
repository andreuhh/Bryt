"""Post-activity analysis triage: which runs deserve the full MechanicalLoadAgent.

Most runs of a week are easy: their deterministic metrics plus a short note on a cheap model
are enough. The full analysis runs when (1) the plan called for a quality/key session, (2) the
run was not easy in practice (time above Z2, variable pace, unusual distance or descent,
far from the planned volume), or (3) a red flag shows up (mechanical breakdown, cardiac
decoupling, high RPE, feeling unwell, poor morning check-in). Whatever cannot be judged
(no zones, little history) also gets the full analysis: a wrong LIGHT loses a signal, a
wrong FULL only costs a few cents.

Zones come from the athlete's calibration (§5): the thresholds below are escalation policy,
not physiological values.
"""

from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo

import pandas as pd
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Activity, ActivityStream, User, UserLifestyleProfile, Workout
from app.models.enums import AnalysisDepth, WorkoutType
from app.schemas.activity import ComputedMetrics, ContextTags
from app.schemas.context import AnalysisTriage, ElevationQuality, TrainingBaseline
from app.schemas.training import AthleteCalibration
from app.services.fit_parser import DEFAULT_THRESHOLDS
from app.services.history import elevation_quality, training_baseline
from app.services.wellness import wellness_summary

EASY_TYPES = frozenset({WorkoutType.EASY, WorkoutType.RECOVERY})
# A run on a rest/strength day is judged on its data, like an unplanned run
UNPLANNED_TYPES = frozenset({WorkoutType.REST, WorkoutType.STRENGTH})
EASY_ZONE = "Z2"


@dataclass(frozen=True)
class TriageThresholds:
    max_time_above_easy_pct: float = 15.0  # of moving time above the top of Z2
    max_speed_cv: float = DEFAULT_THRESHOLDS.variable_speed_cv  # above → intervals/fartlek
    max_distance_vs_typical: float = 1.5  # × the average run of the last 28 days
    max_descent_vs_typical: float = 2.0  # × the athlete's usual descent per km
    min_descent_m_per_km: float = 15.0  # below this a route is flat for anyone
    max_planned_deviation_pct: float = 25.0  # distance/duration vs the planned session
    # Pa:Hr drift: 5-8% is common on easy runs (heat, HR drift) and not a mechanical risk
    max_decoupling_pct: float = 10.0
    max_easy_rpe: int = 6  # perceived effort above this is not easy
    min_feeling: int = 3  # morning check-in 1-2 (exhausted) → full analysis
    min_history_runs: int = 4  # fewer runs in 28 days → no yardstick for "usual"
    smoothing_samples: int = 5  # rolling median against GPS/HR spikes
    moving_speed_mps: float = DEFAULT_THRESHOLDS.moving_speed_mps


DEFAULT_TRIAGE = TriageThresholds()


def time_above_easy_pct(
    stream: ActivityStream | None,
    calibration: AthleteCalibration,
    th: TriageThresholds = DEFAULT_TRIAGE,
) -> float | None:
    """% of moving time above Z2: by HR when the run has HR and the athlete HR zones, else by
    pace. None when neither can be judged."""
    z2 = next((z for z in calibration.zones if z.code == EASY_ZONE), None)
    if stream is None or z2 is None or stream.sample_count < th.smoothing_samples:
        return None
    df = pd.DataFrame(
        {
            "t": stream.elapsed_s,
            "pace": pd.to_numeric(pd.Series(stream.pace_s_per_km), errors="coerce"),
            "hr": pd.to_numeric(pd.Series(stream.heart_rate), errors="coerce"),
        }
    )
    dt = df["t"].diff().fillna(0).clip(lower=0)
    dt = dt.clip(upper=3 * max(float(dt[dt > 0].median() or 1.0), 1.0))  # pauses don't count
    moving = df["pace"].notna() & (df["pace"] <= 1000 / th.moving_speed_mps)

    def smooth(series: pd.Series) -> pd.Series:
        return series.rolling(th.smoothing_samples, min_periods=1, center=True).median()

    if z2.hr is not None and df["hr"].notna().sum() > len(df) / 2:
        above = smooth(df["hr"]) > z2.hr.max_bpm
    elif z2.pace is not None:
        above = smooth(df["pace"]) < z2.pace.fast_s_per_km
    else:
        return None
    total = float(dt[moving].sum())
    if total <= 0:
        return None
    return round(100 * float(dt[moving & above].sum()) / total, 1)


def triage(
    activity: Activity,
    planned: Workout | None,
    baseline: TrainingBaseline,
    elevation: ElevationQuality,
    above_easy_pct: float | None,
    feeling: int | None,
    *,
    reanalysis: bool,
    th: TriageThresholds = DEFAULT_TRIAGE,
) -> AnalysisTriage:
    reasons: list[str] = []
    if reanalysis:  # the athlete asked again: give them the full analysis
        reasons.append("re-analysis requested by the athlete")

    # 1. What was planned
    if planned is not None and planned.workout_type not in UNPLANNED_TYPES:
        if planned.is_key_session:
            reasons.append(f"planned key session ({planned.workout_type})")
        elif planned.workout_type not in EASY_TYPES:
            reasons.append(f"planned {planned.workout_type} session")
        else:
            reasons += _planned_deviation(activity, planned, th)

    # 2. What actually happened
    if above_easy_pct is None:
        reasons.append("intensity unknown (no HR/pace zones or no usable stream)")
    elif above_easy_pct > th.max_time_above_easy_pct:
        reasons.append(f"{above_easy_pct:.0f}% of moving time above {EASY_ZONE}")
    metrics = (
        ComputedMetrics.model_validate(activity.computed_metrics)
        if activity.computed_metrics
        else None
    )
    if metrics and metrics.speed_cv is not None and metrics.speed_cv > th.max_speed_cv:
        reasons.append(f"variable pace (speed CV {metrics.speed_cv:.2f}): intervals or fartlek")
    if baseline.activities < th.min_history_runs:
        reasons.append(f"only {baseline.activities} runs in the last 28 days: no usual yardstick")
    else:
        typical_km = baseline.total_km / baseline.activities
        km = activity.distance_m / 1000
        if km > th.max_distance_vs_typical * typical_km:
            reasons.append(f"{km:.1f} km vs a usual run of {typical_km:.1f} km")
        if elevation.reliable is not False and activity.elevation_loss_m and km > 0:
            descent = activity.elevation_loss_m / km
            usual = (baseline.total_elevation_loss_m or 0) / baseline.total_km
            if descent > max(th.min_descent_m_per_km, th.max_descent_vs_typical * usual):
                reasons.append(f"descent {descent:.0f} m/km vs a usual {usual:.0f} m/km")

    # 3. Red flags
    if metrics and metrics.cadence_hr_divergence.mechanical_breakdown:
        reasons.append("mechanical breakdown detected in the final segment")
    decoupling = metrics.aerobic_decoupling_pct if metrics else None
    if decoupling is not None and decoupling > th.max_decoupling_pct:
        reasons.append(f"aerobic decoupling {decoupling:.1f}%")
    tags = ContextTags.model_validate(activity.context_tags or {})
    if tags.rpe is not None and tags.rpe > th.max_easy_rpe:
        reasons.append(f"RPE {tags.rpe}/10")
    if tags.feeling_unwell:
        reasons.append("athlete felt unwell")
    if feeling is not None and feeling < th.min_feeling:
        reasons.append(f"morning check-in feeling {feeling}/5")

    return AnalysisTriage(
        depth=AnalysisDepth.FULL if reasons else AnalysisDepth.LIGHT,
        reasons=reasons,
        time_above_easy_pct=above_easy_pct,
    )


def _planned_deviation(activity: Activity, planned: Workout, th: TriageThresholds) -> list[str]:
    pairs = (
        ("distance", activity.distance_m, planned.target_distance_m),
        ("duration", activity.moving_time_s or activity.duration_s, planned.target_duration_s),
    )
    for label, done, target in pairs:
        if target:
            deviation = 100 * (done - target) / target
            if abs(deviation) > th.max_planned_deviation_pct:
                return [f"{label} {deviation:+.0f}% vs the planned easy run"]
    return []


async def triage_activity(
    session: AsyncSession,
    user: User,
    activity: Activity,
    calibration: AthleteCalibration,
    *,
    reanalysis: bool,
) -> AnalysisTriage:
    planned = (
        await session.exec(
            select(Workout).where(Workout.user_id == user.id, Workout.activity_id == activity.id)
        )
    ).first()
    stream = (
        await session.exec(
            select(ActivityStream).where(
                ActivityStream.user_id == user.id, ActivityStream.activity_id == activity.id
            )
        )
    ).first()
    profile = (
        await session.exec(
            select(UserLifestyleProfile).where(UserLifestyleProfile.user_id == user.id)
        )
    ).first()
    baseline = await training_baseline(
        session,
        user.id,
        activity.start_time,
        exclude_activity_id=activity.id,
        declared_weekly_km=profile.weekly_volume_km if profile else None,
    )
    day: date = activity.start_time.astimezone(ZoneInfo(user.timezone)).date()
    check_in = (await wellness_summary(session, user.id, day)).check_in
    return triage(
        activity,
        planned,
        baseline,
        elevation_quality(activity, stream),
        time_above_easy_pct(stream, calibration),
        check_in.feeling if check_in else None,
        reanalysis=reanalysis,
    )
