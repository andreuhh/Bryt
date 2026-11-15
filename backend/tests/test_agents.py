"""Agent layer: calibration, plan generation/adjustment, post-activity pipeline, endpoints."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, time, timedelta

import httpx
import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agents.context import local_today
from app.agents.llm import AgentUnavailableError, get_llm
from app.agents.pipeline import get_pipeline_launcher, run_post_activity_pipeline
from app.agents.scheduler import get_plan_job_launcher
from app.agents.training_periodization import build_plan, refine_plan, start_plan_generation
from app.core.database import get_session
from app.main import app
from app.models import AgentExecutionLog, PersonalBest, TrainingPlan, User, Workout
from app.models.enums import (
    ActivitySource,
    AgentName,
    AgentRunStatus,
    AthleteBackground,
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
        _pb(10000, 2280, 900),  # old and faster: ignored while a recent one exists
        _pb(21097, 5070, 60),
        _pb(10000, 2100, 30, Surface.TRAIL),  # trail: ignored for pace
    ]
    cal = compute_calibration(_profile(), pbs, date(2026, 11, 15))
    assert cal.threshold_pace_s_per_km == pytest.approx(riegel_threshold_pace(pbs[1]), abs=0.1)
    assert "ultimi 12 mesi" in cal.source_notes
    zones = {z.code: z for z in cal.zones}
    assert zones["Z4"].hr is not None and zones["Z4"].hr.max_bpm == round(172 * 0.99)
    # Easier zones are slower: Z2 slow bound > Z4 slow bound
    assert zones["Z2"].pace and zones["Z4"].pace
    assert zones["Z2"].pace.slow_s_per_km > zones["Z4"].pace.slow_s_per_km


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

    async def _launch(user_id: uuid.UUID, activity_id: uuid.UUID) -> None:
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
    assert report["nutrition_recovery"]["output"]["nutrition_protocol"]["caffeine"]

    feedback = await client.post(
        f"/agent-runs/{report['nutrition_recovery']['id']}/feedback",
        headers=_h(athlete),
        json={"feedback": "UP", "comment": "utile"},
    )
    assert feedback.status_code == 200 and feedback.json()["feedback"] == "UP"


async def test_context_tags_rerun_pipeline(
    api: tuple[httpx.AsyncClient, FakeLLM, list[tuple[uuid.UUID, uuid.UUID]]], athlete: User
) -> None:
    client, _, launched = api
    files = {"file": ("run.fit", build_fit(synthetic_run(30)), "application/octet-stream")}
    activity_id = (
        await client.post("/activities/upload-fit", headers=_h(athlete), files=files)
    ).json()["activity"]["id"]
    response = await client.patch(
        f"/activities/{activity_id}/context",
        headers=_h(athlete),
        json={"surface": "ASPHALT", "context_tags": {"caffeine_mg": 200, "jet_lag_hours": 6}},
    )
    assert response.status_code == 200
    assert response.json()["context_tags"]["jet_lag_hours"] == 6
    assert len(launched) == 2  # upload + tags


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
