"""Post-activity analysis triage (pure): which runs get the full MechanicalLoadAgent."""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.models import Activity, ActivityStream, Workout
from app.models.enums import (
    ActivitySource,
    AnalysisDepth,
    CalibrationConfidence,
    DataCoverage,
    WorkoutType,
)
from app.schemas.context import ElevationQuality, TrainingBaseline
from app.schemas.training import AthleteCalibration, HrRange, PaceRange, TrainingZone
from app.services.triage import time_above_easy_pct, triage

USER = uuid.uuid4()
RELIABLE = ElevationQuality(reliable=True, reason="ok")
CALIBRATION = AthleteCalibration(
    confidence=CalibrationConfidence.HIGH,
    threshold_pace_s_per_km=240,
    threshold_hr=172,
    zones=[
        TrainingZone(
            code="Z2",
            label="Aerobico",
            hr=HrRange(min_bpm=146, max_bpm=153),
            pace=PaceRange(fast_s_per_km=274, slow_s_per_km=310),
        )
    ],
    source_notes="test",
)


def _baseline(activities: int = 12, total_km: float = 120, loss_m: float = 600) -> TrainingBaseline:
    return TrainingBaseline(
        window_days=28,
        data_coverage=DataCoverage.HIGH,
        habitual_window_days=56,
        habitual_weekly_km=30,
        activities=activities,
        total_km=total_km,
        weekly_avg_km=total_km / 4,
        acute_7d_km=30,
        total_elevation_loss_m=loss_m,
    )


def _activity(**kw: Any) -> Activity:
    data: dict[str, Any] = {
        "user_id": USER,
        "source": ActivitySource.MANUAL_UPLOAD,
        "start_time": datetime(2026, 11, 17, 7, tzinfo=UTC),
        "duration_s": 3600,
        "moving_time_s": 3600,
        "distance_m": 10_000,
        "elevation_loss_m": 50,
        "computed_metrics": {
            "speed_cv": 0.05,
            "aerobic_decoupling_pct": 2.0,
            "cadence_hr_divergence": {"evaluated": True, "mechanical_breakdown": False},
        },
    }
    return Activity(**(data | kw))


def _easy(**kw: Any) -> Workout:
    data: dict[str, Any] = {
        "user_id": USER,
        "plan_id": uuid.uuid4(),
        "scheduled_date": datetime(2026, 11, 17).date(),
        "workout_type": WorkoutType.EASY,
        "title": "Easy",
        "target_distance_m": 10_000,
    }
    return Workout(**(data | kw))


def _run(
    activity: Activity | None = None,
    planned: Workout | None = None,
    *,
    baseline: TrainingBaseline | None = None,
    above: float | None = 3.0,
    feeling: int | None = None,
    reanalysis: bool = False,
) -> tuple[AnalysisDepth, list[str]]:
    result = triage(
        activity or _activity(),
        planned,
        baseline or _baseline(),
        RELIABLE,
        above,
        feeling,
        reanalysis=reanalysis,
    )
    return result.depth, result.reasons


def test_easy_run_as_planned_is_light() -> None:
    assert _run(planned=_easy()) == (AnalysisDepth.LIGHT, [])
    assert _run() == (AnalysisDepth.LIGHT, [])  # unplanned but easy in the data


@pytest.mark.parametrize(
    ("planned", "expected"),
    [
        (_easy(workout_type=WorkoutType.THRESHOLD), "planned THRESHOLD session"),
        (_easy(workout_type=WorkoutType.LONG), "planned LONG session"),
        (_easy(is_key_session=True), "planned key session (EASY)"),
        (_easy(target_distance_m=7_000), "distance +43% vs the planned easy run"),
    ],
)
def test_quality_or_off_plan_sessions_are_full(planned: Workout, expected: str) -> None:
    assert _run(planned=planned) == (AnalysisDepth.FULL, [expected])


def test_run_on_a_rest_day_is_judged_on_its_data() -> None:
    assert _run(planned=_easy(workout_type=WorkoutType.REST))[0] == AnalysisDepth.LIGHT


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"above": 30.0}, "30% of moving time above Z2"),
        ({"above": None}, "intensity unknown (no HR/pace zones or no usable stream)"),
        ({"baseline": _baseline(activities=2)}, "only 2 runs in the last 28 days"),
        ({"activity": _activity(distance_m=16_000)}, "16.0 km vs a usual run of 10.0 km"),
        ({"activity": _activity(elevation_loss_m=400)}, "descent 40 m/km vs a usual 5 m/km"),
        ({"feeling": 2}, "morning check-in feeling 2/5"),
        ({"reanalysis": True}, "re-analysis requested by the athlete"),
    ],
)
def test_hard_or_unknown_runs_are_full(kwargs: dict[str, Any], expected: str) -> None:
    depth, reasons = _run(**kwargs)
    assert depth == AnalysisDepth.FULL
    assert reasons[0].startswith(expected)


def test_red_flags_escalate_an_easy_run() -> None:
    """Includes the case a cheaper model once missed: RPE 10 on a planned easy run."""
    metrics = {
        "speed_cv": 0.25,
        "aerobic_decoupling_pct": 12.0,
        "cadence_hr_divergence": {"evaluated": True, "mechanical_breakdown": True},
    }
    activity = _activity(computed_metrics=metrics, context_tags={"rpe": 10, "feeling_unwell": True})
    depth, reasons = _run(activity, _easy())
    assert depth == AnalysisDepth.FULL
    assert len(reasons) == 5  # variable pace, breakdown, decoupling, RPE, unwell


def test_unreliable_altitude_is_not_read_as_descent() -> None:
    result = triage(
        _activity(elevation_loss_m=400),
        None,
        _baseline(),
        ElevationQuality(reliable=False, reason="GPS"),
        3.0,
        None,
        reanalysis=False,
    )
    assert result.depth == AnalysisDepth.LIGHT


def _stream(hr: list[float | None], pace: list[float | None]) -> ActivityStream:
    return ActivityStream(
        user_id=USER,
        activity_id=uuid.uuid4(),
        sample_count=len(hr),
        elapsed_s=[float(i) for i in range(len(hr))],
        pace_s_per_km=pace,
        heart_rate=hr,
    )


def test_time_above_easy_by_hr_ignores_spikes_and_stops() -> None:
    hr: list[float | None] = [150.0] * 60 + [165.0] * 40
    hr[10] = 190  # single spike: smoothed away
    pace: list[float | None] = [290.0] * 100
    pace[20:30] = [None] * 10  # stopped: not moving time
    assert time_above_easy_pct(_stream(hr, pace), CALIBRATION) == pytest.approx(
        100 * 40 / 89, abs=0.1
    )  # first sample: dt 0


def test_time_above_easy_falls_back_to_pace_without_hr() -> None:
    pace: list[float | None] = [290.0] * 75 + [250.0] * 25
    assert time_above_easy_pct(_stream([None] * 100, pace), CALIBRATION) == pytest.approx(25, abs=1)
    no_zones = CALIBRATION.model_copy(update={"zones": []})
    assert time_above_easy_pct(_stream([None] * 100, pace), no_zones) is None
