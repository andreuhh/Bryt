import uuid
from datetime import date, datetime, time, timedelta
from typing import Annotated, TypeVar
from zoneinfo import ZoneInfo

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from pydantic import ValidationError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agents.llm import LLMClient, get_llm
from app.agents.pipeline import (
    PipelineLauncher,
    agents_disabled,
    analyses_left,
    get_pipeline_launcher,
    run_post_activity_pipeline,
)
from app.api.deps import CurrentUser, SessionDep
from app.core.config import get_settings
from app.models import Activity, ActivityStream, AgentExecutionLog, User
from app.models.enums import ActivitySource, AgentName, AgentTrigger, SurfaceSource
from app.schemas.activity import ActivityContextUpdate, ActivityRead, ActivityStreamRead
from app.schemas.agent_log import (
    ActivityReport,
    AgentExecutionLogRead,
    MechanicalLoadRun,
    NutritionRecoveryRun,
    PlanAdjustmentRun,
)
from app.schemas.ingestion import UploadFitResult
from app.services.fit_files import InvalidFitFileError, extract_fit_bytes
from app.services.fit_parser import FitParseError, UnsupportedSportError
from app.services.ingestion import ingest_fit
from app.services.storage import FitStorage, get_fit_storage

router = APIRouter(prefix="/activities", tags=["activities"])

LauncherDep = Annotated[PipelineLauncher, Depends(get_pipeline_launcher)]


async def _owned(session: AsyncSession, user: User, activity_id: uuid.UUID) -> Activity:
    activity = await session.get(Activity, activity_id)
    if activity is None or activity.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Activity not found")
    return activity


@router.post(
    "/upload-fit",
    response_model=UploadFitResult,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "File already ingested"}, 413: {}, 422: {}},
)
async def upload_fit(
    response: Response,
    user: CurrentUser,
    session: SessionDep,
    background: BackgroundTasks,
    launch_pipeline: LauncherDep,
    storage: Annotated[FitStorage, Depends(get_fit_storage)],
    file: Annotated[UploadFile, File(description=".fit, .fit.gz or Garmin .zip export")],
    analyze: Annotated[
        bool,
        Query(
            description="false: the client collects context tags first, then starts the analysis"
        ),
    ] = True,
) -> UploadFitResult:
    max_bytes = get_settings().max_fit_upload_mb * 1024 * 1024
    raw = await file.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "File too large")

    try:
        fit_bytes = extract_fit_bytes(raw, max_bytes)
        name = (file.filename or "").split(".")[0] or None
        result = await ingest_fit(
            session,
            user=user,
            fit_bytes=fit_bytes,
            source=ActivitySource.MANUAL_UPLOAD,
            storage=storage,
            name=name,
        )
    except (InvalidFitFileError, FitParseError, UnsupportedSportError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    if result.created and analyze:
        background.add_task(launch_pipeline, user.id, result.activity.id)
    elif not result.created:
        response.status_code = status.HTTP_200_OK
    return UploadFitResult(
        created=result.created, activity=ActivityRead.model_validate(result.activity)
    )


@router.get("", response_model=list[ActivityRead])
async def list_activities(
    user: CurrentUser,
    session: SessionDep,
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 20,
) -> list[ActivityRead]:
    """Most recent first. `from`/`to` are local dates (athlete's time zone), inclusive."""
    tz = ZoneInfo(user.timezone)
    stmt = select(Activity).where(Activity.user_id == user.id)
    if start is not None:
        stmt = stmt.where(col(Activity.start_time) >= datetime.combine(start, time.min, tz))
    if end is not None:
        stmt = stmt.where(
            col(Activity.start_time) < datetime.combine(end + timedelta(days=1), time.min, tz)
        )
    stmt = stmt.order_by(col(Activity.start_time).desc()).limit(limit)
    return [ActivityRead.model_validate(a) for a in (await session.exec(stmt)).all()]


@router.get("/{activity_id}", response_model=ActivityRead)
async def read_activity(
    activity_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> ActivityRead:
    return ActivityRead.model_validate(await _owned(session, user, activity_id))


@router.get("/{activity_id}/streams", response_model=ActivityStreamRead)
async def read_streams(
    activity_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> ActivityStreamRead:
    await _owned(session, user, activity_id)
    stream = (
        await session.exec(select(ActivityStream).where(ActivityStream.activity_id == activity_id))
    ).first()
    if stream is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No streams for this activity")
    return ActivityStreamRead.model_validate(stream)


@router.patch("/{activity_id}/context", response_model=ActivityRead)
async def update_context(
    activity_id: uuid.UUID,
    body: ActivityContextUpdate,
    user: CurrentUser,
    session: SessionDep,
    background: BackgroundTasks,
    launch_pipeline: LauncherDep,
    analyze: bool = False,
) -> ActivityRead:
    """Post-activity quick tags (surface, caffeine, jet lag…). `analyze=true` runs the agent
    pipeline (first analysis after an upload); editing tags later never re-spends on its own:
    the athlete asks for a new analysis explicitly (POST /analyze)."""
    activity = await _owned(session, user, activity_id)
    if analyze:
        await _ensure_analysis_allowed(session, user, activity_id, launch_pipeline)
    if body.surface is not None:
        activity.surface = body.surface
        activity.surface_source = SurfaceSource.USER
    activity.context_tags = body.context_tags.model_dump(mode="json", exclude_none=True)
    session.add(activity)
    await session.commit()
    await session.refresh(activity)
    if analyze:
        background.add_task(launch_pipeline, user.id, activity.id)
    return ActivityRead.model_validate(activity)


@router.post("/{activity_id}/analyze", response_model=ActivityReport)
async def analyze_now(
    activity_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    response: Response,
    background: BackgroundTasks,
    launch_pipeline: LauncherDep,
    llm: Annotated[LLMClient, Depends(get_llm)],
    run_in_background: Annotated[bool, Query(alias="background")] = False,
) -> ActivityReport:
    """Runs the agent pipeline. `background=true`: 202 now, poll GET /report (UI);
    otherwise waits for the whole pipeline (debug)."""
    activity = await _owned(session, user, activity_id)
    await _ensure_analysis_allowed(session, user, activity_id, launch_pipeline)
    if run_in_background:
        background.add_task(launch_pipeline, user.id, activity.id)
        response.status_code = status.HTTP_202_ACCEPTED
    else:
        await run_post_activity_pipeline(session, llm, user, activity)
    return await read_report(activity_id, user, session)


async def _ensure_analysis_allowed(
    session: SessionDep, user: User, activity_id: uuid.UUID, launch: PipelineLauncher
) -> None:
    # A 202 with agents off would leave the client polling for a report that never comes
    if agents_disabled(launch):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Agents are disabled")
    if await analyses_left(session, user.id, activity_id) == 0:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Analysis limit reached for this activity"
        )


@router.get("/{activity_id}/report", response_model=ActivityReport)
async def read_report(
    activity_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> ActivityReport:
    """Latest pipeline run for the activity (one entry per agent; missing = not run/failed)."""
    await _owned(session, user, activity_id)
    logs = list(
        (
            await session.exec(
                select(AgentExecutionLog)
                .where(
                    AgentExecutionLog.user_id == user.id,
                    AgentExecutionLog.activity_id == activity_id,
                    AgentExecutionLog.trigger == AgentTrigger.POST_ACTIVITY,
                )
                .order_by(col(AgentExecutionLog.created_at).desc())
            )
        ).all()
    )
    left = await analyses_left(session, user.id, activity_id)
    if not logs:
        return ActivityReport(activity_id=activity_id, pipeline_run_id=None, analyses_left=left)
    run_id = logs[0].pipeline_run_id
    latest = {log.agent_name: log for log in reversed(logs) if log.pipeline_run_id == run_id}

    mechanical_log = latest.get(AgentName.MECHANICAL_LOAD)
    mechanical = _typed_run(mechanical_log, MechanicalLoadRun)
    if mechanical and mechanical_log:  # runs before the triage existed stay None (= full)
        triage = mechanical_log.input_snapshot.get("context", {}).get("triage") or {}
        mechanical.depth = triage.get("depth")
    return ActivityReport(
        activity_id=activity_id,
        pipeline_run_id=run_id,
        analyses_left=left,
        mechanical_load=mechanical,
        plan_adjustment=_typed_run(latest.get(AgentName.TRAINING_PERIODIZATION), PlanAdjustmentRun),
        nutrition_recovery=_typed_run(
            latest.get(AgentName.NUTRITION_RECOVERY), NutritionRecoveryRun
        ),
    )


RunT = TypeVar("RunT", MechanicalLoadRun, PlanAdjustmentRun, NutritionRecoveryRun)


def _typed_run(log: AgentExecutionLog | None, model: type[RunT]) -> RunT | None:
    """Outputs stored under an older schema degrade to output=None instead of failing."""
    if log is None:
        return None
    data = AgentExecutionLogRead.model_validate(log).model_dump()
    data.pop("agent_name"), data.pop("trigger"), data.pop("pipeline_run_id")
    data.pop("activity_id"), data.pop("plan_id")
    try:
        return model.model_validate(data)
    except ValidationError:
        data["output"] = None
        data["error"] = (data["error"] or "") + " [output not compatible with the current schema]"
        return model.model_validate(data)
