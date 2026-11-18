"""Agent layer: calibration, plan generation/adjustment, post-activity pipeline, endpoints."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, time, timedelta

import httpx
import pytest
from sqlalchemy import Update
from sqlmodel import col, select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agents.context import local_today
from app.agents.llm import AgentUnavailableError, get_llm
from app.agents.pipeline import (
    claim_analysis,
    get_pipeline_launcher,
    run_post_activity_pipeline,
)
from app.agents.scheduler import get_plan_job_launcher
from app.agents.training_periodization import build_plan, refine_plan, start_plan_generation
from app.core.config import get_settings
from app.core.database import get_session
from app.main import app
from app.models import Activity, AgentExecutionLog, PersonalBest, TrainingPlan, User, Workout
from app.models.enums import (
    ActivitySource,
    AgentName,
    AgentRunStatus,
    AthleteBackground,
    CalibrationConfidence,
    DataCoverage,
    PlanStatus,
    RevisionSource,
    RevisionStatus,
    Surface,
    TrainingSlot,
    WorkoutDetail,
    WorkoutStatus,
    WorkoutType,
    WorkType,
)
from app.models.user import UserLifestyleProfile
from app.schemas.agents import (
    BlockWorkoutsOutput,
    CoachChatOutput,
    MechanicalLoadOutput,
    NutritionRecoveryOutput,
    PlanAdjustmentOutput,
    PlanSkeletonOutput,
    RefinementOutput,
)
from app.schemas.user import OnboardingPayload
from app.services.calibration import compute_calibration, riegel_threshold_pace
from app.services.ingestion import ingest_fit
from app.services.profile import save_onboarding
from app.services.storage import LocalFitStorage
from tests.agent_fakes import (
    FakeLLM,
    adjust_all,
    block_workouts,
    chat_output,
    mechanical_output,
    no_adjustment_mechanical,
    nutrition_output,
    refinement,
    skeleton_output,
)
from tests.factories import profile_payload
from tests.fit_builder import build_fit, synthetic_run

ALL_DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


# --- Calibration (pure) -------------------------------------------------------------------


def _profile(**kw: object) -> UserLifestyleProfile:
    base: dict[str, object] = {
        "user_id": uuid.uuid4(),
        "background": AthleteBackground.ROAD,
        "preferred_slot": TrainingSlot.MORNING,
        "work_type": WorkType.SEDENTARY,
        "threshold_hr": 172,
    }
    return UserLifestyleProfile(**(base | kw))


def _pb(
    distance: int, time_s: int, days_ago: int, surface: Surface = Surface.ASPHALT
) -> PersonalBest:
    return PersonalBest(
        user_id=uuid.uuid4(),
        distance_m=distance,
        time_s=time_s,
        achieved_on=date(2026, 11, 15) - timedelta(days=days_ago),
        surface=surface,
    )


def test_riegel_threshold_from_marathon() -> None:
    # 3:05:12 marathon → ~4:07/km sustainable for 60'
    assert riegel_threshold_pace(_pb(42195, 11112, 10)) == pytest.approx(247, abs=2)


def test_calibration_prefers_recent_flat_pbs_and_builds_zones() -> None:
    pbs = [
        _pb(10000, 2280, 900),  # faster but 30 months old: max age penalty (+8%)
        _pb(21097, 5070, 60),
        _pb(10000, 2100, 30, Surface.TRAIL),  # trail: ignored for pace
    ]
    cal = compute_calibration(_profile(), pbs, date(2026, 11, 15))
    assert cal.threshold_pace_s_per_km == pytest.approx(riegel_threshold_pace(pbs[1]), abs=0.1)
    assert cal.confidence == CalibrationConfidence.HIGH
    zones = {z.code: z for z in cal.zones}
    assert zones["Z4"].hr is not None and zones["Z4"].hr.max_bpm == round(172 * 0.99)
    # Easier zones are slower: Z2 slow bound > Z4 slow bound
    assert zones["Z2"].pace and zones["Z4"].pace
    assert zones["Z2"].pace.slow_s_per_km > zones["Z4"].pace.slow_s_per_km


def test_calibration_keeps_older_fast_pb_with_age_penalty() -> None:
    """Marathons limited by muscular fade must not hide an older, faster 10k."""
    marathon = _pb(42195, 12070, 358)  # 3:21:10, within 12 months
    ten_k = _pb(10000, 2280, 457)  # 38:00, 15 months old
    cal = compute_calibration(_profile(), [marathon, ten_k], date(2026, 11, 15))
    penalty = (457 / 30.44 - 6) * 0.004
    assert cal.threshold_pace_s_per_km == pytest.approx(
        riegel_threshold_pace(ten_k) * (1 + penalty), abs=0.2
    )
    assert cal.threshold_pace_s_per_km < riegel_threshold_pace(marathon)
    assert cal.confidence == CalibrationConfidence.LOW
    assert "penalità età" in cal.source_notes


def test_calibration_estimates_threshold_hr_from_max() -> None:
    cal = compute_calibration(_profile(threshold_hr=None, max_hr=190), [], date(2026, 11, 15))
    assert cal.threshold_hr == 171
    assert cal.threshold_pace_s_per_km is None
    assert "nessun PB" in cal.source_notes


# --- Fixtures -----------------------------------------------------------------------------


@pytest.fixture
async def athlete(session: AsyncSession, user: User) -> User:
    race = local_today(user) + timedelta(weeks=16)
    payload = OnboardingPayload.model_validate(
        {
            "profile": profile_payload(
                available_days=ALL_DAYS,
                target_race_date=race.isoformat(),
                target_race_distance_m=42195,
                target_race_time_s=10500,
                weight_kg=68,
            ),
            "personal_bests": [
                {
                    "distance_m": 42195,
                    "time_s": 11112,
                    "achieved_on": (local_today(user) - timedelta(days=200)).isoformat(),
                }
            ],
        }
    )
    await save_onboarding(session, user, payload)
    return user


async def _active_plan_with_workouts(
    session: AsyncSession, user: User, days: int = 4
) -> list[Workout]:
    today = local_today(user)
    plan = TrainingPlan(
        user_id=user.id,
        name="Piano",
        status=PlanStatus.ACTIVE,
        methodology="TRADITIONAL",  # type: ignore[arg-type]
        start_date=today - timedelta(days=7),
        end_date=today + timedelta(days=60),
    )
    session.add(plan)
    await session.flush()
    workouts = [
        Workout(
            user_id=user.id,
            plan_id=plan.id,
            scheduled_date=today + timedelta(days=i),
            workout_type=WorkoutType.THRESHOLD if i == 1 else WorkoutType.EASY,
            title=f"Workout +{i}",
        )
        for i in range(0, days + 1)
    ]
    session.add_all(workouts)
    await session.commit()
    return workouts


async def _ingest_today(
    session: AsyncSession, user: User, storage: LocalFitStorage, **run: int
) -> object:
    start = datetime.combine(local_today(user), time(6, 0), tzinfo=UTC)
    result = await ingest_fit(
        session,
        user=user,
        fit_bytes=build_fit(synthetic_run(70, **run), start=start),
        source=ActivitySource.MANUAL_UPLOAD,
        storage=storage,
    )
    return result.activity


# --- Plan generation (skeleton + blocks) -------------------------------------------------


def _queue_full_plan(llm: FakeLLM, plan: TrainingPlan) -> FakeLLM:
    return llm.queue(PlanSkeletonOutput, skeleton_output(plan.start_date, plan.end_date)).queue(
        BlockWorkoutsOutput, block_workouts(), block_workouts()
    )


async def _built_plan(session: AsyncSession, user: User) -> TrainingPlan:
    plan = await start_plan_generation(session, user)
    await build_plan(session, _queue_full_plan(FakeLLM(), plan), user, plan)
    return plan


async def _plan_workouts(session: AsyncSession, plan: TrainingPlan) -> list[Workout]:
    stmt = select(Workout).where(Workout.plan_id == plan.id).order_by(col(Workout.scheduled_date))
    return list((await session.exec(stmt)).all())


async def test_build_plan_covers_every_day_with_detail_levels(
    session: AsyncSession, athlete: User
) -> None:
    today = local_today(athlete)
    old = TrainingPlan(
        user_id=athlete.id,
        name="Vecchio",
        status=PlanStatus.ACTIVE,
        methodology="TRADITIONAL",  # type: ignore[arg-type]
        start_date=today,
        end_date=today + timedelta(days=30),
    )
    session.add(old)
    await session.commit()

    plan = await start_plan_generation(session, athlete)
    assert plan.status == PlanStatus.GENERATING
    assert plan.end_date == today + timedelta(weeks=16)  # race day from the profile
    llm = _queue_full_plan(FakeLLM(), plan)
    await build_plan(session, llm, athlete, plan)

    await session.refresh(old)
    assert plan.status == PlanStatus.ACTIVE and old.status == PlanStatus.ARCHIVED
    assert plan.last_refined_on == today
    workouts = await _plan_workouts(session, plan)
    expected_days = (plan.end_date - plan.start_date).days + 1
    assert len({w.scheduled_date for w in workouts}) == expected_days == len(workouts)

    horizon = today + timedelta(days=14)
    for w in workouts:
        confirmed = w.scheduled_date <= horizon
        assert w.detail_level == (
            WorkoutDetail.CONFIRMED if confirmed else WorkoutDetail.PROVISIONAL
        )
        assert w.is_key_session == (w.scheduled_date.weekday() == 6)
        if w.workout_type == WorkoutType.THRESHOLD:
            has_pace = w.structure[0].get("target_pace") is not None
            assert has_pace == confirmed  # provisional sessions carry zones only

    block_calls = llm.calls_for(BlockWorkoutsOutput)
    assert block_calls[0].context["previous_block_last_week"] == []
    assert len(block_calls[1].context["previous_block_last_week"]) == 7  # continuity
    assert all(c.cache_prefix for c in block_calls)  # blocks re-read the cached skeleton


async def test_build_plan_repairs_missing_day(session: AsyncSession, athlete: User) -> None:
    plan = await start_plan_generation(session, athlete)
    llm = (
        FakeLLM()
        .queue(PlanSkeletonOutput, skeleton_output(plan.start_date, plan.end_date))
        .queue(
            BlockWorkoutsOutput,
            block_workouts(skip=plan.start_date + timedelta(days=3)),
            block_workouts(),
            block_workouts(),
        )
    )
    await build_plan(session, llm, athlete, plan)
    calls = llm.calls_for(BlockWorkoutsOutput)
    assert len(calls) == 3 and "missing days" in calls[1].prompt
    assert plan.status == PlanStatus.ACTIVE


async def test_build_plan_failure_keeps_previous_plan(session: AsyncSession, athlete: User) -> None:
    previous = await _built_plan(session, athlete)
    plan = await start_plan_generation(session, athlete)
    llm = (
        FakeLLM()
        .queue(PlanSkeletonOutput, skeleton_output(plan.start_date, plan.end_date))
        .queue(BlockWorkoutsOutput, block_workouts(), AgentUnavailableError("rate limit"))
    )
    with pytest.raises(AgentUnavailableError):
        await build_plan(session, llm, athlete, plan)

    failed = await session.get(TrainingPlan, plan.id)
    assert failed is not None and failed.status == PlanStatus.FAILED
    assert "rate limit" in (failed.generation_error or "")
    assert await _plan_workouts(session, failed) == []  # no half plan left behind
    await session.refresh(previous)
    assert previous.status == PlanStatus.ACTIVE


# --- Weekly refinement & proposals --------------------------------------------------------


async def _age_window(session: AsyncSession, plan: TrainingPlan, today: date) -> list[Workout]:
    """Simulates time passing: the next 2 weeks become provisional again (paces stripped)."""
    aged = []
    for w in await _plan_workouts(session, plan):
        if today < w.scheduled_date <= today + timedelta(days=14):
            w.detail_level = WorkoutDetail.PROVISIONAL
            w.structure = [
                {k: v for k, v in s.items() if k not in ("target_pace", "target_hr")}
                for s in w.structure
            ]
            session.add(w)
            aged.append(w)
    plan.last_refined_on = today - timedelta(days=7)
    session.add(plan)
    await session.commit()
    return aged


async def test_refine_confirms_window_and_proposes_far_key_session(
    session: AsyncSession, athlete: User
) -> None:
    plan = await _built_plan(session, athlete)
    today = local_today(athlete)
    aged = await _age_window(session, plan, today)

    llm = FakeLLM().queue(RefinementOutput, refinement(propose_first_key=True))
    confirmed, proposals, output = await refine_plan(session, llm, athlete)

    assert {w.id for w in confirmed} == {w.id for w in aged}
    assert all(w.detail_level == WorkoutDetail.CONFIRMED for w in confirmed)
    tuesday = next(w for w in confirmed if w.workout_type == WorkoutType.THRESHOLD)
    assert tuesday.structure[0]["target_pace"] is not None
    assert len(proposals) == 1 and proposals[0].status == RevisionStatus.PENDING
    key = await session.get(Workout, proposals[0].workout_id)
    assert (
        key is not None and key.is_key_session and key.scheduled_date > today + timedelta(days=14)
    )
    assert key.status == WorkoutStatus.PLANNED  # not applied until the athlete accepts
    assert plan.last_refined_on == today

    # Nothing provisional left in the window → no model call
    again = FakeLLM()
    assert await refine_plan(session, again, athlete) == ([], [], None)
    assert again.calls == []


def test_refinement_due_rules() -> None:
    from app.agents.scheduler import refinement_due

    sunday_evening = datetime(2026, 11, 15, 20, 30)  # a Sunday
    assert refinement_due(None, sunday_evening)
    assert refinement_due(date(2026, 11, 8), sunday_evening)
    assert not refinement_due(date(2026, 11, 15), sunday_evening)  # already done today
    assert not refinement_due(date(2026, 11, 12), datetime(2026, 11, 15, 18, 0))  # too early
    assert refinement_due(date(2026, 11, 8), datetime(2026, 11, 16, 9, 0))  # Monday catch-up


async def test_claim_refinement_is_exclusive(session: AsyncSession, athlete: User) -> None:
    from app.agents.scheduler import claim_refinement

    plan = await _built_plan(session, athlete)
    tomorrow = local_today(athlete) + timedelta(days=1)
    assert await claim_refinement(session, plan.id, tomorrow) is True
    assert await claim_refinement(session, plan.id, tomorrow) is False


# --- Post-activity pipeline ---------------------------------------------------------------


async def test_pipeline_full_cascade_with_adjustment(
    session: AsyncSession, athlete: User, storage: LocalFitStorage
) -> None:
    workouts = await _active_plan_with_workouts(session, athlete)
    activity = await _ingest_today(session, athlete, storage, final_cadence_drop=6)

    llm = (
        FakeLLM()
        .queue(MechanicalLoadOutput, mechanical_output())  # days_affected = 3
        .queue(PlanAdjustmentOutput, adjust_all("REDUCE"))
        .queue(NutritionRecoveryOutput, nutrition_output())
    )
    result = await run_post_activity_pipeline(session, llm, athlete, activity)  # type: ignore[arg-type]

    assert result.errors == []
    assert result.mechanical and result.adjustment and result.nutrition
    ml_ctx = llm.calls_for(MechanicalLoadOutput)[0].context
    assert ml_ctx["activity"]["computed_metrics"]["cadence_hr_divergence"]["mechanical_breakdown"]
    assert ml_ctx["planned_workout"]["title"] == "Workout +0"  # today's run linked to the plan

    reviewed = llm.calls_for(PlanAdjustmentOutput)[0].context["workouts_to_review"]
    assert [w["title"] for w in reviewed] == ["Workout +1", "Workout +2", "Workout +3"]
    for w in workouts[1:4]:
        await session.refresh(w)
        assert w.status == WorkoutStatus.MODIFIED
        assert w.original_snapshot and w.original_snapshot["title"].startswith("Workout +")
    await session.refresh(workouts[4])
    assert workouts[4].status == WorkoutStatus.PLANNED  # outside days_affected

    nr_ctx = llm.calls_for(NutritionRecoveryOutput)[0].context
    assert nr_ctx["plan_adjustment"]["rationale"]
    logs = (
        await session.exec(
            select(AgentExecutionLog).where(AgentExecutionLog.pipeline_run_id == result.run_id)
        )
    ).all()
    assert {log.agent_name for log in logs} == {
        AgentName.MECHANICAL_LOAD,
        AgentName.TRAINING_PERIODIZATION,
        AgentName.NUTRITION_RECOVERY,
    }
    # Each agent runs (and is logged) on its own model
    settings = get_settings()
    assert {log.agent_name: log.model for log in logs} == {
        AgentName.MECHANICAL_LOAD: settings.anthropic_model,
        AgentName.TRAINING_PERIODIZATION: settings.anthropic_model,
        AgentName.NUTRITION_RECOVERY: settings.nutrition_recovery_model,
    }
    assert llm.calls_for(NutritionRecoveryOutput)[0].model == settings.nutrition_recovery_model
    # One-shot calls skip the cache write (nobody re-reads their prefix)
    for output_model in (MechanicalLoadOutput, PlanAdjustmentOutput, NutritionRecoveryOutput):
        assert llm.calls_for(output_model)[0].cache_prefix is False
    # Cost from the logged tokens (FakeLLM: 100 input, 50 output)
    from app.agents.pricing import PRICES

    haiku = PRICES[settings.nutrition_recovery_model]
    nutrition_log = next(log for log in logs if log.agent_name == AgentName.NUTRITION_RECOVERY)
    assert nutrition_log.cost_usd == pytest.approx((100 * haiku.input + 50 * haiku.output) / 1e6)


def test_cost_is_unknown_for_unpriced_models() -> None:
    from app.agents.pricing import cost_usd

    tokens = {
        "input_tokens": 1_000_000,
        "output_tokens": None,
        "cache_creation_input_tokens": None,
        "cache_read_input_tokens": 1_000_000,
    }
    assert cost_usd("claude-opus-5-5", **tokens) == pytest.approx(4.2)
    assert cost_usd("fake-model", **tokens) is None


def test_model_for_falls_back_to_default_model() -> None:
    from app.core.config import Settings

    settings = Settings(anthropic_model="m-default", coach_chat_model="m-chat")
    assert settings.model_for(AgentName.COACH_CHAT) == "m-chat"
    assert settings.model_for(AgentName.MECHANICAL_LOAD) == "m-default"


async def test_easy_run_gets_light_analysis_and_full_on_reanalysis(
    session: AsyncSession, athlete: User, storage: LocalFitStorage
) -> None:
    from app.api.v1.endpoints.activities import read_report

    await _active_plan_with_workouts(session, athlete)  # today: planned EASY
    start = datetime.combine(local_today(athlete), time(6, 0), tzinfo=UTC)
    session.add_all(  # enough history to judge what a usual run is
        Activity(
            user_id=athlete.id,
            source=ActivitySource.MANUAL_UPLOAD,
            start_time=start - timedelta(days=2 + 3 * i),
            duration_s=4200,
            distance_m=14_000,
        )
        for i in range(5)
    )
    await session.commit()
    activity = await _ingest_today(session, athlete, storage)  # HR below the top of Z2

    def run_llm() -> FakeLLM:
        return (
            FakeLLM()
            .queue(MechanicalLoadOutput, no_adjustment_mechanical())
            .queue(NutritionRecoveryOutput, nutrition_output())
        )

    settings = get_settings()
    light = run_llm()
    result = await run_post_activity_pipeline(session, light, athlete, activity)  # type: ignore[arg-type]
    assert result.errors == []
    call = light.calls_for(MechanicalLoadOutput)[0]
    assert call.context["triage"]["depth"] == "LIGHT"
    assert (call.model, call.effort) == (settings.mechanical_load_light_model, "low")
    assert "easy run with no red flags" in call.prompt
    report = await read_report(activity.id, athlete, session)
    assert report.mechanical_load and report.mechanical_load.depth == "LIGHT"
    assert report.mechanical_load.model == settings.mechanical_load_light_model

    # The athlete asks again: full analysis on the agent's own model
    full = run_llm()
    await run_post_activity_pipeline(session, full, athlete, activity)  # type: ignore[arg-type]
    call = full.calls_for(MechanicalLoadOutput)[0]
    assert call.context["triage"]["reasons"] == ["re-analysis requested by the athlete"]
    assert (call.model, call.effort) == (settings.anthropic_model, "medium")


async def test_light_analysis_cannot_adjust_the_plan(
    session: AsyncSession, athlete: User, storage: LocalFitStorage
) -> None:
    start = datetime.combine(local_today(athlete), time(6, 0), tzinfo=UTC)
    session.add_all(
        Activity(
            user_id=athlete.id,
            source=ActivitySource.MANUAL_UPLOAD,
            start_time=start - timedelta(days=2 + 3 * i),
            duration_s=4200,
            distance_m=14_000,
        )
        for i in range(5)
    )
    await session.commit()
    activity = await _ingest_today(session, athlete, storage)
    no_breakdown = mechanical_output(alerts=[])  # asks for an adjustment
    llm = (
        FakeLLM()
        .queue(MechanicalLoadOutput, no_breakdown, no_adjustment_mechanical())
        .queue(NutritionRecoveryOutput, nutrition_output())
    )
    result = await run_post_activity_pipeline(session, llm, athlete, activity)  # type: ignore[arg-type]
    assert result.errors == [] and result.adjustment is None
    assert "plan_adjustment_needed must be false" in llm.calls_for(MechanicalLoadOutput)[1].prompt
    assert not llm.calls_for(PlanAdjustmentOutput)


async def test_pipeline_without_adjustment_skips_periodization(
    session: AsyncSession, athlete: User, storage: LocalFitStorage
) -> None:
    activity = await _ingest_today(session, athlete, storage)
    llm = (
        FakeLLM()
        .queue(MechanicalLoadOutput, no_adjustment_mechanical())
        .queue(NutritionRecoveryOutput, nutrition_output())
    )
    result = await run_post_activity_pipeline(session, llm, athlete, activity)  # type: ignore[arg-type]
    assert result.adjustment is None and result.nutrition is not None
    assert not llm.calls_for(PlanAdjustmentOutput)


async def test_missing_breakdown_alert_triggers_repair(
    session: AsyncSession, athlete: User, storage: LocalFitStorage
) -> None:
    activity = await _ingest_today(session, athlete, storage, final_cadence_drop=6)
    llm = (
        FakeLLM()
        .queue(
            MechanicalLoadOutput,
            no_adjustment_mechanical(),
            mechanical_output(plan_adjustment_needed=False, adjustment_request=None),
        )
        .queue(NutritionRecoveryOutput, nutrition_output())
    )
    result = await run_post_activity_pipeline(session, llm, athlete, activity)  # type: ignore[arg-type]
    assert result.errors == []
    assert len(llm.calls_for(MechanicalLoadOutput)) == 2
    assert "mechanical breakdown" in llm.calls_for(MechanicalLoadOutput)[1].prompt


async def test_pipeline_stops_and_logs_when_llm_unavailable(
    session: AsyncSession, athlete: User, storage: LocalFitStorage
) -> None:
    activity = await _ingest_today(session, athlete, storage)
    llm = FakeLLM().queue(MechanicalLoadOutput, AgentUnavailableError("no credentials"))
    result = await run_post_activity_pipeline(session, llm, athlete, activity)  # type: ignore[arg-type]
    assert result.mechanical is None and result.errors
    log = (
        await session.exec(
            select(AgentExecutionLog).where(AgentExecutionLog.pipeline_run_id == result.run_id)
        )
    ).one()
    assert log.status == AgentRunStatus.ERROR and "no credentials" in (log.error or "")


def _set_started(activity_id: uuid.UUID, at: datetime | None) -> Update:
    return update(Activity).where(col(Activity.id) == activity_id).values(analysis_started_at=at)


async def test_one_pipeline_per_activity_at_a_time(
    session: AsyncSession, athlete: User, storage: LocalFitStorage
) -> None:
    activity = await _ingest_today(session, athlete, storage)
    assert await claim_analysis(session, activity.id)  # e.g. the backend poll got there first
    llm = FakeLLM()
    skipped = await run_post_activity_pipeline(session, llm, athlete, activity)  # type: ignore[arg-type]
    assert skipped.errors == ["analysis already running"] and not llm.calls

    await session.exec(_set_started(activity.id, None))  # the first run ends
    llm.queue(MechanicalLoadOutput, no_adjustment_mechanical())
    llm.queue(NutritionRecoveryOutput, nutrition_output())
    done = await run_post_activity_pipeline(session, llm, athlete, activity)  # type: ignore[arg-type]
    assert done.errors == []
    assert await claim_analysis(session, activity.id)  # released when the run ends


async def test_stale_claim_of_a_crashed_run_expires(
    session: AsyncSession, athlete: User, storage: LocalFitStorage
) -> None:
    activity = await _ingest_today(session, athlete, storage)
    crashed = datetime.now(UTC) - timedelta(hours=1)
    await session.exec(_set_started(activity.id, crashed))
    assert await claim_analysis(session, activity.id)


# --- HTTP endpoints -----------------------------------------------------------------------


@pytest.fixture
async def api(
    session: AsyncSession, storage: LocalFitStorage
) -> AsyncIterator[tuple[httpx.AsyncClient, FakeLLM, list[tuple[uuid.UUID, uuid.UUID]]]]:
    from app.services.storage import get_fit_storage

    llm = FakeLLM()
    launched: list[tuple[uuid.UUID, uuid.UUID]] = []

    async def _session() -> AsyncIterator[AsyncSession]:
        yield session

    async def _launch(user_id: uuid.UUID, activity_id: uuid.UUID, *, claimed: bool = False) -> None:
        launched.append((user_id, activity_id))

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_fit_storage] = lambda: storage
    app.dependency_overrides[get_llm] = lambda: llm
    app.dependency_overrides[get_pipeline_launcher] = lambda: _launch

    async def _build_inline(user_id: uuid.UUID, plan_id: uuid.UUID) -> None:
        user = await session.get(User, user_id)
        plan = await session.get(TrainingPlan, plan_id)
        assert user is not None and plan is not None
        await build_plan(session, _queue_full_plan(llm, plan), user, plan)

    app.dependency_overrides[get_plan_job_launcher] = lambda: _build_inline
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c, llm, launched
    app.dependency_overrides.clear()


def _h(user: User) -> dict[str, str]:
    return {"X-Dev-User-Id": str(user.id)}


async def test_upload_launches_pipeline_once_and_report_endpoint(
    api: tuple[httpx.AsyncClient, FakeLLM, list[tuple[uuid.UUID, uuid.UUID]]], athlete: User
) -> None:
    client, llm, launched = api
    files = {"file": ("run.fit", build_fit(synthetic_run(30)), "application/octet-stream")}
    first = await client.post("/activities/upload-fit", headers=_h(athlete), files=files)
    await client.post("/activities/upload-fit", headers=_h(athlete), files=files)  # duplicate
    activity_id = first.json()["activity"]["id"]
    assert launched == [(athlete.id, uuid.UUID(activity_id))]

    empty = await client.get(f"/activities/{activity_id}/report", headers=_h(athlete))
    assert empty.json()["pipeline_run_id"] is None

    llm.queue(MechanicalLoadOutput, no_adjustment_mechanical())
    llm.queue(NutritionRecoveryOutput, nutrition_output())
    report = (await client.post(f"/activities/{activity_id}/analyze", headers=_h(athlete))).json()
    assert report["mechanical_load"]["status"] == "SUCCESS"
    assert report["plan_adjustment"] is None
    # The morning check-in (empty here) reaches both post-activity agents
    for model in (MechanicalLoadOutput, NutritionRecoveryOutput):
        assert '"wellness"' in llm.calls_for(model)[-1].prompt
    assert report["nutrition_recovery"]["output"]["nutrition_protocol"]["caffeine"]

    feedback = await client.post(
        f"/agent-runs/{report['nutrition_recovery']['id']}/feedback",
        headers=_h(athlete),
        json={"feedback": "UP", "comment": "utile"},
    )
    assert feedback.status_code == 200 and feedback.json()["feedback"] == "UP"


async def test_context_tags_analyze_only_on_request(
    api: tuple[httpx.AsyncClient, FakeLLM, list[tuple[uuid.UUID, uuid.UUID]]], athlete: User
) -> None:
    client, _, launched = api
    files = {"file": ("run.fit", build_fit(synthetic_run(30)), "application/octet-stream")}
    activity_id = (
        await client.post("/activities/upload-fit", headers=_h(athlete), files=files)
    ).json()["activity"]["id"]
    body = {"surface": "ASPHALT", "context_tags": {"caffeine_mg": 200, "jet_lag_hours": 6}}

    # Editing tags later: saved, no new (paid) analysis on its own
    response = await client.patch(
        f"/activities/{activity_id}/context", headers=_h(athlete), json=body
    )
    assert response.status_code == 200
    assert response.json()["context_tags"]["jet_lag_hours"] == 6
    assert response.json()["surface_source"] == "USER"
    assert len(launched) == 1  # the upload only

    # Post-upload modal ("Salva e analizza")
    response = await client.patch(
        f"/activities/{activity_id}/context?analyze=true", headers=_h(athlete), json=body
    )
    assert response.status_code == 200
    assert len(launched) == 2


async def test_one_reanalysis_per_activity(
    api: tuple[httpx.AsyncClient, FakeLLM, list[tuple[uuid.UUID, uuid.UUID]]], athlete: User
) -> None:
    """Cost cap: the first analysis + one after editing the tags, then 429 (tags still saved
    without analysis)."""
    client, llm, _ = api
    files = {"file": ("run.fit", build_fit(synthetic_run(30)), "application/octet-stream")}
    activity_id = (
        await client.post("/activities/upload-fit", headers=_h(athlete), files=files)
    ).json()["activity"]["id"]
    report = (await client.get(f"/activities/{activity_id}/report", headers=_h(athlete))).json()
    assert report["analyses_left"] == 2

    for left in (1, 0):
        llm.queue(MechanicalLoadOutput, no_adjustment_mechanical())
        llm.queue(NutritionRecoveryOutput, nutrition_output())
        report = (
            await client.post(f"/activities/{activity_id}/analyze", headers=_h(athlete))
        ).json()
        assert report["analyses_left"] == left

    calls = len(llm.calls)
    over = await client.post(f"/activities/{activity_id}/analyze", headers=_h(athlete))
    assert over.status_code == 429
    tags = {"context_tags": {"rpe": 6}}
    refused = await client.patch(
        f"/activities/{activity_id}/context?analyze=true", headers=_h(athlete), json=tags
    )
    assert refused.status_code == 429
    saved = await client.patch(f"/activities/{activity_id}/context", headers=_h(athlete), json=tags)
    assert saved.status_code == 200 and saved.json()["context_tags"]["rpe"] == 6
    assert len(llm.calls) == calls  # nothing spent past the cap


async def test_other_users_cannot_read_activity(
    api: tuple[httpx.AsyncClient, FakeLLM, list[tuple[uuid.UUID, uuid.UUID]]], athlete: User
) -> None:
    client, _, _ = api
    files = {"file": ("run.fit", build_fit(synthetic_run(30)), "application/octet-stream")}
    activity_id = (
        await client.post("/activities/upload-fit", headers=_h(athlete), files=files)
    ).json()["activity"]["id"]
    stranger = {"X-Dev-User-Id": str(uuid.uuid4())}
    assert (await client.get(f"/activities/{activity_id}", headers=stranger)).status_code == 404


async def test_generate_plan_endpoint_requires_onboarding(
    api: tuple[httpx.AsyncClient, FakeLLM, list[tuple[uuid.UUID, uuid.UUID]]],
) -> None:
    client, _, _ = api
    response = await client.post("/plans/generate", headers={"X-Dev-User-Id": str(uuid.uuid4())})
    assert response.status_code == 409


async def test_chat_proposes_then_adjust_applies(
    api: tuple[httpx.AsyncClient, FakeLLM, list[tuple[uuid.UUID, uuid.UUID]]],
    session: AsyncSession,
    athlete: User,
) -> None:
    client, llm, _ = api
    await _active_plan_with_workouts(session, athlete)
    llm.queue(CoachChatOutput, chat_output(with_adjustment=True))
    chat = await client.post(
        "/chat",
        headers=_h(athlete),
        json={"messages": [{"role": "user", "content": "Ho la febbre, cosa faccio?"}]},
    )
    assert chat.status_code == 200, chat.text
    body = chat.json()
    assert body["proposed_adjustment"]["days_affected"] == 3
    assert "Athlete: Ho la febbre" in llm.calls[-1].prompt

    llm.queue(PlanAdjustmentOutput, adjust_all("REST"))
    applied = await client.post(
        "/plans/adjust", headers=_h(athlete), json={"adjustment": body["proposed_adjustment"]}
    )
    assert applied.status_code == 200, applied.text
    modified = applied.json()["modified"]
    # Window includes today: today, +1, +2
    assert len(modified) == 3
    assert all(w["workout_type"] == "REST" and w["status"] == "MODIFIED" for w in modified)

    week = await client.get("/workouts", headers=_h(athlete))
    assert week.status_code == 200 and week.json()


async def test_chat_caches_shared_state_and_enforces_daily_quota(
    api: tuple[httpx.AsyncClient, FakeLLM, list[tuple[uuid.UUID, uuid.UUID]]],
    session: AsyncSession,
    athlete: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, llm, _ = api
    await _active_plan_with_workouts(session, athlete)
    monkeypatch.setattr(get_settings(), "chat_daily_limit", 2)
    body = {"messages": [{"role": "user", "content": "Ciao"}]}

    llm.queue(CoachChatOutput, AgentUnavailableError("down"))
    assert (await client.post("/chat", headers=_h(athlete), json=body)).status_code == 503
    quota = (await client.get("/chat/quota", headers=_h(athlete))).json()
    assert quota == {"limit": 2, "used": 0, "remaining": 2}  # failed calls don't count

    for remaining in (1, 0):
        llm.queue(CoachChatOutput, chat_output(with_adjustment=False))
        response = await client.post("/chat", headers=_h(athlete), json=body)
        assert response.status_code == 200, response.text
        assert response.json()["quota"]["remaining"] == remaining

    # Plan and recent activities are in the cached prefix; only the transcript varies
    prefix = llm.calls[-1].cached_prefix or ""
    assert "upcoming_workouts" in prefix and "recent_activities" in prefix
    assert "upcoming_workouts" not in llm.calls[-1].prompt

    calls = len(llm.calls)
    over = await client.post("/chat", headers=_h(athlete), json=body)
    assert over.status_code == 429
    assert len(llm.calls) == calls  # no LLM call once the quota is used up


async def test_agent_unavailable_maps_to_503(
    api: tuple[httpx.AsyncClient, FakeLLM, list[tuple[uuid.UUID, uuid.UUID]]], athlete: User
) -> None:
    client, llm, _ = api
    llm.queue(CoachChatOutput, AgentUnavailableError("Anthropic credentials missing"))
    response = await client.post(
        "/chat", headers=_h(athlete), json={"messages": [{"role": "user", "content": "Ciao"}]}
    )
    assert response.status_code == 503


# --- Data quality -------------------------------------------------------------------------


def _act_stream(gain: float, loss: float, alts: list[float]) -> tuple[object, object]:
    from app.models import Activity, ActivityStream

    act = Activity(
        user_id=uuid.uuid4(),
        source=ActivitySource.MANUAL_UPLOAD,
        start_time=datetime(2026, 11, 15, tzinfo=UTC),
        duration_s=3000,
        distance_m=10000,
        elevation_gain_m=gain,
        elevation_loss_m=loss,
    )
    stream = ActivityStream(
        user_id=act.user_id, activity_id=act.id, sample_count=len(alts), elevation_m=alts
    )
    return act, stream


def test_elevation_quality_consistent_barometric_data() -> None:
    from app.services.history import elevation_quality

    hill = [40 + i * 0.1 for i in range(500)] + [90 - i * 0.1 for i in range(500)]
    act, stream = _act_stream(50, 50, hill)
    assert elevation_quality(act, stream).reliable is True  # type: ignore[arg-type]


def test_elevation_quality_flags_gps_like_altitude() -> None:
    """Same pattern as a real Suunto 5 Peak file: device says +16/-0, series wanders 22 m."""
    import math

    from app.services.history import elevation_quality

    wander = [36 + 11 * math.sin(i / 400) for i in range(3000)]
    act, stream = _act_stream(16, 0, wander)
    quality = elevation_quality(act, stream)  # type: ignore[arg-type]
    assert quality.reliable is False
    assert "GPS" in quality.reason


# --- AnthropicLLM error mapping -----------------------------------------------------------


class _RaisingStream:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    async def __aenter__(self) -> None:
        raise self.exc

    async def __aexit__(self, *args: object) -> None:
        return None


class _FakeAnthropic:
    """Mimics AsyncAnthropic.beta.messages.stream raising at request time."""

    def __init__(self, exc: Exception) -> None:
        outer = self

        class _Messages:
            def stream(self, **kwargs: object) -> _RaisingStream:
                outer.kwargs = kwargs
                return _RaisingStream(exc)

        class _Beta:
            messages = _Messages()

        self.beta = _Beta()
        self.kwargs: dict[str, object] = {}


async def test_anthropic_llm_missing_credentials_is_unavailable() -> None:
    from app.agents.llm import AnthropicLLM

    fake = _FakeAnthropic(
        TypeError('"Could not resolve authentication method. Expected one of api_key..."')
    )
    llm = AnthropicLLM(model="claude-opus-5-5", client=fake)  # type: ignore[arg-type]
    with pytest.raises(AgentUnavailableError):
        await llm.generate(
            system="s", prompt="p", output_model=CoachChatOutput, effort="low", max_tokens=100
        )
    # Request shape: structured output, adaptive thinking, effort, server-side fallbacks
    assert fake.kwargs["output_format"] is CoachChatOutput
    assert fake.kwargs["thinking"] == {"type": "adaptive"}
    assert fake.kwargs["output_config"] == {"effort": "low"}
    assert fake.kwargs["fallbacks"] == "default"
    assert fake.kwargs["betas"] == ["server-side-fallback-2026-07-01"]


async def test_anthropic_llm_other_type_errors_propagate() -> None:
    from app.agents.llm import AnthropicLLM

    llm = AnthropicLLM(client=_FakeAnthropic(TypeError("bug")))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        await llm.generate(
            system="s", prompt="p", output_model=CoachChatOutput, effort="low", max_tokens=100
        )


# --- Plan endpoints -----------------------------------------------------------------------


async def test_generate_endpoint_returns_202_then_plan_is_active(
    api: tuple[httpx.AsyncClient, FakeLLM, list[tuple[uuid.UUID, uuid.UUID]]], athlete: User
) -> None:
    client, _, _ = api
    started = await client.post("/plans/generate", headers=_h(athlete))
    assert started.status_code == 202 and started.json()["status"] == "GENERATING"
    plan = (await client.get(f"/plans/{started.json()['id']}", headers=_h(athlete))).json()
    assert plan["status"] == "ACTIVE" and len(plan["blocks"]) == 2

    keys = (await client.get("/workouts?key_only=true", headers=_h(athlete))).json()
    assert keys and all(w["is_key_session"] for w in keys)
    assert {date.fromisoformat(w["scheduled_date"]).weekday() for w in keys} == {6}
    assert keys[-1]["detail_level"] == "PROVISIONAL"  # far ahead, zones only


async def test_generate_endpoint_rejects_concurrent_generation(
    api: tuple[httpx.AsyncClient, FakeLLM, list[tuple[uuid.UUID, uuid.UUID]]],
    session: AsyncSession,
    athlete: User,
) -> None:
    client, _, _ = api
    await start_plan_generation(session, athlete)  # stays GENERATING
    response = await client.post("/plans/generate", headers=_h(athlete))
    assert response.status_code == 409


async def test_proposals_accept_reject_and_history(
    api: tuple[httpx.AsyncClient, FakeLLM, list[tuple[uuid.UUID, uuid.UUID]]],
    session: AsyncSession,
    athlete: User,
) -> None:
    from app.services.workouts import propose

    client, llm, _ = api
    plan = await _built_plan(session, athlete)
    await _age_window(session, plan, local_today(athlete))

    llm.queue(RefinementOutput, refinement(propose_first_key=True))
    refined = (await client.post("/plans/active/refine", headers=_h(athlete))).json()
    assert refined["confirmed"] and refined["notes"] == "Settimana confermata."

    pending = (await client.get("/plans/active/proposals", headers=_h(athlete))).json()
    assert len(pending) == 1
    proposal = pending[0]
    accepted = await client.post(f"/plans/proposals/{proposal['id']}/accept", headers=_h(athlete))
    assert accepted.status_code == 200
    moved = accepted.json()
    assert moved["scheduled_date"] == proposal["after"]["scheduled_date"]
    assert moved["status"] == "MODIFIED" and moved["title"] == "Lungo 32 km"
    again = await client.post(f"/plans/proposals/{proposal['id']}/accept", headers=_h(athlete))
    assert again.status_code == 409

    hist = (await client.get(f"/workouts/{moved['id']}/history", headers=_h(athlete))).json()
    assert [h["status"] for h in hist] == ["APPLIED"]
    assert "cedimento" in hist[0]["reason"]

    # A second proposal on the same session, rejected
    workout = await session.get(Workout, uuid.UUID(moved["id"]))
    assert workout is not None
    from app.schemas.training import WorkoutDraft

    rev = await propose(
        session,
        workout,
        WorkoutDraft.model_validate(proposal["before"]),
        reason="Torna alla data originale",
        agent_run_id=None,
    )
    await session.commit()
    rejected = await client.post(f"/plans/proposals/{rev.id}/reject", headers=_h(athlete))
    assert (
        rejected.status_code == 200 and rejected.json()["scheduled_date"] == moved["scheduled_date"]
    )
    assert (await client.get("/plans/active/proposals", headers=_h(athlete))).json() == []


async def test_post_activity_adjustment_is_recorded_in_history(
    session: AsyncSession, athlete: User, storage: LocalFitStorage
) -> None:
    workouts = await _active_plan_with_workouts(session, athlete)
    activity = await _ingest_today(session, athlete, storage, final_cadence_drop=6)
    llm = (
        FakeLLM()
        .queue(MechanicalLoadOutput, mechanical_output())
        .queue(PlanAdjustmentOutput, adjust_all("REDUCE"))
        .queue(NutritionRecoveryOutput, nutrition_output())
    )
    await run_post_activity_pipeline(session, llm, athlete, activity)  # type: ignore[arg-type]
    from app.services.workouts import history

    revs = await history(session, workouts[1].id)
    assert len(revs) == 1
    assert (
        revs[0].source == RevisionSource.POST_ACTIVITY and revs[0].status == RevisionStatus.APPLIED
    )
    assert revs[0].before and revs[0].before["title"] == "Workout +1"


# --- Profile v2: coverage, key-session cap, double sessions, caching ----------------------


async def test_baseline_uses_declared_volume_when_history_is_sparse(
    session: AsyncSession, athlete: User, storage: LocalFitStorage
) -> None:
    from app.services.history import training_baseline

    await _ingest_today(session, athlete, storage)  # a single recorded run
    later = datetime.combine(local_today(athlete) + timedelta(days=1), time.min, tzinfo=UTC)
    sparse = await training_baseline(session, athlete.id, later, declared_weekly_km=72)
    assert sparse.data_coverage == DataCoverage.LOW
    assert sparse.effective_weekly_km == 72
    assert sparse.acute_chronic_ratio is None  # meaningless on sparse data

    no_declared = await training_baseline(session, athlete.id, later)
    assert no_declared.effective_weekly_km == no_declared.weekly_avg_km


async def test_baseline_reads_post_race_dip_as_real_volume(
    session: AsyncSession, athlete: User
) -> None:
    """Complete recordings: 4 weeks at ~72 km, then marathon + recovery at ~30 km/week."""
    from app.services.history import training_baseline

    now = datetime(2026, 11, 16, tzinfo=UTC)
    race_day = date(2026, 11, 1)
    for day in range(56, 0, -1):
        start = now - timedelta(days=day)
        if start.weekday() in (1, 3, 5, 6) and start.date() != race_day:
            km = 18 if day > 28 else 5  # habitual block, then taper/recovery
            session.add(
                Activity(
                    user_id=athlete.id,
                    source=ActivitySource.INTERVALS,
                    external_id=f"a{day}",
                    start_time=start,
                    duration_s=km * 300,
                    distance_m=km * 1000,
                )
            )
    session.add(
        Activity(
            user_id=athlete.id,
            source=ActivitySource.INTERVALS,
            external_id="nyc",
            start_time=datetime.combine(race_day, time(14, 0), tzinfo=UTC),
            duration_s=12298,
            distance_m=42195,
        )
    )
    session.add(
        PersonalBest(
            user_id=athlete.id,
            distance_m=42195,
            time_s=12298,
            achieved_on=race_day,
            surface=Surface.ASPHALT,
            event_name="NYC Marathon",
        )
    )
    await session.commit()

    base = await training_baseline(session, athlete.id, now, declared_weekly_km=72)
    assert base.weekly_avg_km < 0.5 * 72  # the old 28-day rule would call this missing data
    assert base.data_coverage == DataCoverage.HIGH
    assert base.effective_weekly_km == base.weekly_avg_km
    assert base.acute_chronic_ratio is not None
    assert base.habitual_weekly_km > base.weekly_avg_km
    assert len(base.weekly_km) == 8 and base.weekly_km[0] == 72
    assert [r.name for r in base.recent_races] == ["NYC Marathon"]
    assert base.recent_races[0].days_ago == 15
    assert base.recent_races[0].recovery_until == date(2026, 11, 28)
    assert base.in_post_race_recovery


async def test_block_validator_caps_key_sessions_and_double_runs(
    session: AsyncSession, athlete: User
) -> None:
    from app.agents.training_periodization import _block_violations
    from app.schemas.training import PlanBlock

    profile = (
        await session.exec(
            select(UserLifestyleProfile).where(UserLifestyleProfile.user_id == athlete.id)
        )
    ).one()
    cal = compute_calibration(profile, [], local_today(athlete))
    monday = date(2026, 11, 16)
    block = PlanBlock.model_validate(
        {
            "name": "B",
            "phase": "BASE",
            "start_date": monday.isoformat(),
            "end_date": (monday + timedelta(days=6)).isoformat(),
            "objective": "x",
            "weeks": [{"week_index": 1, "start_date": monday.isoformat(), "load_type": "LOAD"}],
        }
    )

    def day(i: int, **kw: object) -> dict[str, object]:
        base = {
            "scheduled_date": (monday + timedelta(days=i)).isoformat(),
            "workout_type": "EASY",
            "title": f"d{i}",
            "target_duration_s": 3000,
        }
        return base | kw

    workouts = [day(i, is_key_session=True) for i in range(7)]  # 7 "key" sessions
    workouts += [day(1, session_slot="PM", title="PM run")]  # double run on Tuesday
    workouts += [day(2, workout_type="STRENGTH", title="Forza a casa")]  # strength: not a run
    out = BlockWorkoutsOutput.model_validate({"workouts": workouts})
    available = set(ALL_DAYS)

    single = _block_violations(out, block, available, cal, double_ok=False)
    assert any("key sessions" in v for v in single)
    assert any("more than 1 run" in v for v in single)
    assert not any(str(monday + timedelta(days=2)) in v and "run(s)" in v for v in single)

    double = _block_violations(out, block, available, cal, double_ok=True)
    assert not any("run(s) in a day" in v for v in double)


async def test_patch_profile_and_onboarding_is_idempotent_on_pbs(
    api: tuple[httpx.AsyncClient, FakeLLM, list[tuple[uuid.UUID, uuid.UUID]]],
    session: AsyncSession,
    athlete: User,
) -> None:
    client, _, _ = api
    patched = await client.patch(
        "/me/profile",
        headers=_h(athlete),
        json={
            "weekly_volume_km": 72,
            "peak_volume_km": 82,
            "long_run_day": "SUN",
            "strength_setting": "HOME",
            "coach_notes": "NYC: quadricipiti induriti al km 25",
        },
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["weekly_volume_km"] == 72 and body["long_run_day"] == "SUN"
    assert body["methodology"] == "TRADITIONAL"  # untouched fields keep their value

    payload = {
        "profile": profile_payload(),
        "personal_bests": [{"distance_m": 10000, "time_s": 2280, "achieved_on": "2025-08-15"}],
    }
    for _ in range(2):
        assert (
            await client.put("/me/onboarding", headers=_h(athlete), json=payload)
        ).status_code == 200
    pbs = (await session.exec(select(PersonalBest).where(PersonalBest.user_id == athlete.id))).all()
    assert len([pb for pb in pbs if pb.distance_m == 10000]) == 1


async def test_block_calls_share_a_cached_prefix(session: AsyncSession, athlete: User) -> None:
    plan = await start_plan_generation(session, athlete)
    llm = _queue_full_plan(FakeLLM(), plan)
    await build_plan(session, llm, athlete, plan)
    blocks = llm.calls_for(BlockWorkoutsOutput)
    assert blocks[0].cached_prefix and blocks[0].cached_prefix == blocks[1].cached_prefix
    assert "skeleton" in blocks[0].cached_prefix
    assert "current_block" not in blocks[0].cached_prefix  # the varying part stays out


async def test_anthropic_llm_puts_cache_breakpoint_on_prefix() -> None:
    from app.agents.llm import AnthropicLLM

    fake = _FakeAnthropic(TypeError("Could not resolve authentication method"))
    llm = AnthropicLLM(client=fake)  # type: ignore[arg-type]
    with pytest.raises(AgentUnavailableError):
        await llm.generate(
            system="s",
            prompt="variable",
            output_model=CoachChatOutput,
            effort="low",
            max_tokens=100,
            cached_prefix="stable",
        )
    content = fake.kwargs["messages"][0]["content"]  # type: ignore[index]
    assert content[0] == {"type": "text", "text": "stable", "cache_control": {"type": "ephemeral"}}
    assert content[1] == {"type": "text", "text": "variable"}
    assert "cache_control" not in fake.kwargs


# --- Re-analysis does not stack plan adjustments ------------------------------------------


async def test_reanalysis_replaces_previous_adjustment(
    session: AsyncSession, athlete: User, storage: LocalFitStorage
) -> None:
    from app.services.workouts import history

    workouts = await _active_plan_with_workouts(session, athlete)
    activity = await _ingest_today(session, athlete, storage, final_cadence_drop=6)

    def run_llm(adjust: bool) -> FakeLLM:
        llm = FakeLLM()
        if adjust:
            llm.queue(MechanicalLoadOutput, mechanical_output())
            llm.queue(PlanAdjustmentOutput, adjust_all("REDUCE"))
        else:  # keeps the breakdown alert the deterministic analysis requires
            llm.queue(
                MechanicalLoadOutput,
                mechanical_output(plan_adjustment_needed=False, adjustment_request=None),
            )
        return llm.queue(NutritionRecoveryOutput, nutrition_output())

    await run_post_activity_pipeline(session, run_llm(True), athlete, activity)  # type: ignore[arg-type]
    second = run_llm(True)
    await run_post_activity_pipeline(session, second, athlete, activity)  # type: ignore[arg-type]

    # The second analysis reviewed the ORIGINAL workouts, not the already reduced ones
    reviewed = second.calls_for(PlanAdjustmentOutput)[0].context["workouts_to_review"]
    assert [w["title"] for w in reviewed] == ["Workout +1", "Workout +2", "Workout +3"]
    revs = await history(session, workouts[1].id)
    assert [r.status for r in revs] == [RevisionStatus.SUPERSEDED, RevisionStatus.APPLIED]

    # A third analysis that needs no change restores the original plan
    await run_post_activity_pipeline(session, run_llm(False), athlete, activity)  # type: ignore[arg-type]
    for w in workouts[1:4]:
        await session.refresh(w)
        assert w.status == WorkoutStatus.PLANNED and w.title.startswith("Workout +")
        assert w.original_snapshot is None


async def test_list_activities_date_range(
    api: tuple[httpx.AsyncClient, FakeLLM, list[tuple[uuid.UUID, uuid.UUID]]],
    session: AsyncSession,
    athlete: User,
    storage: LocalFitStorage,
) -> None:
    client, _, _ = api
    await _ingest_today(session, athlete, storage)
    today = local_today(athlete)
    hit = await client.get(f"/activities?from={today}&to={today}", headers=_h(athlete))
    miss = await client.get(
        f"/activities?from={today - timedelta(days=9)}&to={today - timedelta(days=2)}",
        headers=_h(athlete),
    )
    assert len(hit.json()) == 1 and miss.json() == []


async def test_upload_without_analysis_then_background_analyze(
    api: tuple[httpx.AsyncClient, FakeLLM, list[tuple[uuid.UUID, uuid.UUID]]], athlete: User
) -> None:
    """Dashboard flow: upload (no analysis) → tags or skip → exactly one pipeline run."""
    client, _, launched = api
    files = {"file": ("run.fit", build_fit(synthetic_run(30)), "application/octet-stream")}
    up = await client.post("/activities/upload-fit?analyze=false", headers=_h(athlete), files=files)
    assert up.status_code == 201 and launched == []

    activity_id = up.json()["activity"]["id"]
    started = await client.post(
        f"/activities/{activity_id}/analyze?background=true", headers=_h(athlete)
    )
    assert started.status_code == 202
    assert launched == [(athlete.id, uuid.UUID(activity_id))]
    # Claimed before answering: in progress from the first poll, a double click is refused
    assert started.json()["analysis_running"] is True
    again = await client.post(
        f"/activities/{activity_id}/analyze?background=true", headers=_h(athlete)
    )
    assert again.status_code == 409 and len(launched) == 1


async def test_analysis_requests_fail_fast_with_agents_disabled(
    api: tuple[httpx.AsyncClient, FakeLLM, list[tuple[uuid.UUID, uuid.UUID]]], athlete: User
) -> None:
    """AGENTS_ENABLED=false: a 202 would leave the client polling a report that never comes."""
    client, _, _ = api
    files = {"file": ("run.fit", build_fit(synthetic_run(30)), "application/octet-stream")}
    up = await client.post("/activities/upload-fit?analyze=false", headers=_h(athlete), files=files)
    activity_id = up.json()["activity"]["id"]
    app.dependency_overrides.pop(get_pipeline_launcher)  # real one: AGENTS_ENABLED=false in tests

    started = await client.post(
        f"/activities/{activity_id}/analyze?background=true", headers=_h(athlete)
    )
    tagged = await client.patch(
        f"/activities/{activity_id}/context?analyze=true",
        headers=_h(athlete),
        json={"context_tags": {}},
    )
    assert started.status_code == 503 and tagged.status_code == 503


async def test_report_shows_a_run_in_progress_whoever_started_it(
    api: tuple[httpx.AsyncClient, FakeLLM, list[tuple[uuid.UUID, uuid.UUID]]],
    session: AsyncSession,
    athlete: User,
) -> None:
    client, llm, launched = api
    files = {"file": ("run.fit", build_fit(synthetic_run(30)), "application/octet-stream")}
    up = await client.post("/activities/upload-fit?analyze=false", headers=_h(athlete), files=files)
    activity_id = up.json()["activity"]["id"]
    llm.queue(MechanicalLoadOutput, no_adjustment_mechanical())
    llm.queue(NutritionRecoveryOutput, nutrition_output())
    await client.post(f"/activities/{activity_id}/analyze", headers=_h(athlete))

    # A re-analysis started elsewhere (backend poll, another tab): explicit timestamp because
    # now() is frozen inside the test transaction
    await session.exec(_set_started(uuid.UUID(activity_id), datetime.now(UTC)))
    report = (await client.get(f"/activities/{activity_id}/report", headers=_h(athlete))).json()
    assert report["analysis_running"] is True
    assert report["mechanical_load"] is None  # the previous run is being replaced

    again = await client.post(
        f"/activities/{activity_id}/analyze?background=true", headers=_h(athlete)
    )
    assert again.status_code == 409 and launched == []

    await session.exec(_set_started(uuid.UUID(activity_id), None))
    report = (await client.get(f"/activities/{activity_id}/report", headers=_h(athlete))).json()
    assert report["analysis_running"] is False and report["mechanical_load"] is not None


async def test_rerunning_onboarding_keeps_intervals_credentials(
    api: tuple[httpx.AsyncClient, FakeLLM, list[tuple[uuid.UUID, uuid.UUID]]],
    session: AsyncSession,
    athlete: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import intervals_sync

    async def _ok(self: intervals_sync.IntervalsClient) -> dict[str, object]:
        return {}

    monkeypatch.setattr(intervals_sync.IntervalsClient, "get_athlete", _ok)
    client, _, _ = api
    connected = {"profile": profile_payload(intervals_athlete_id="i42", intervals_api_key="k-1")}
    assert (
        await client.put("/me/onboarding", headers=_h(athlete), json=connected)
    ).status_code == 200

    # The wizard cannot pre-fill the write-only key: a re-run without it keeps the connection
    rerun = await client.put(
        "/me/onboarding", headers=_h(athlete), json={"profile": profile_payload()}
    )
    assert rerun.status_code == 200
    assert rerun.json()["intervals_connected"] is True
    assert rerun.json()["intervals_athlete_id"] == "i42"

    pbs = await client.get("/me/personal-bests", headers=_h(athlete))
    assert pbs.status_code == 200 and pbs.json()[0]["distance_m"] == 42195
