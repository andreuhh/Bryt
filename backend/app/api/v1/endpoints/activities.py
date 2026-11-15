import uuid
from typing import Annotated

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
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agents.llm import LLMClient, get_llm
from app.agents.pipeline import PipelineLauncher, get_pipeline_launcher, run_post_activity_pipeline
from app.api.deps import CurrentUser, SessionDep
from app.core.config import get_settings
from app.models import Activity, ActivityStream, AgentExecutionLog, User
from app.models.enums import ActivitySource, AgentName, AgentTrigger
from app.schemas.activity import ActivityContextUpdate, ActivityRead, ActivityStreamRead
from app.schemas.agent_log import ActivityReport, AgentExecutionLogRead
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

    if result.created:
        background.add_task(launch_pipeline, user.id, result.activity.id)
    else:
        response.status_code = status.HTTP_200_OK
    return UploadFitResult(
        created=result.created, activity=ActivityRead.model_validate(result.activity)
    )


@router.get("", response_model=list[ActivityRead])
async def list_activities(
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[ActivityRead]:
    stmt = (
        select(Activity)
        .where(Activity.user_id == user.id)
        .order_by(col(Activity.start_time).desc())
        .limit(limit)
    )
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
) -> ActivityRead:
    """Post-activity quick tags (surface, caffeine, jet lag…). Re-runs the agent pipeline."""
    activity = await _owned(session, user, activity_id)
    if body.surface is not None:
        activity.surface = body.surface
    activity.context_tags = body.context_tags.model_dump(mode="json", exclude_none=True)
    session.add(activity)
    await session.commit()
    await session.refresh(activity)
    background.add_task(launch_pipeline, user.id, activity.id)
    return ActivityRead.model_validate(activity)


@router.post("/{activity_id}/analyze", response_model=ActivityReport)
async def analyze_now(
    activity_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    llm: Annotated[LLMClient, Depends(get_llm)],
) -> ActivityReport:
    """Runs the pipeline synchronously (debug / manual re-run) and returns the report."""
    activity = await _owned(session, user, activity_id)
    await run_post_activity_pipeline(session, llm, user, activity)
    return await read_report(activity_id, user, session)


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
    if not logs:
        return ActivityReport(activity_id=activity_id, pipeline_run_id=None)
    run_id = logs[0].pipeline_run_id
    latest = {log.agent_name: log for log in reversed(logs) if log.pipeline_run_id == run_id}

    def read(name: AgentName) -> AgentExecutionLogRead | None:
        log = latest.get(name)
        return AgentExecutionLogRead.model_validate(log) if log else None

    return ActivityReport(
        activity_id=activity_id,
        pipeline_run_id=run_id,
        mechanical_load=read(AgentName.MECHANICAL_LOAD),
        plan_adjustment=read(AgentName.TRAINING_PERIODIZATION),
        nutrition_recovery=read(AgentName.NUTRITION_RECOVERY),
    )
