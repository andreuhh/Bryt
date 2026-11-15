import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, SessionDep
from app.models import AgentExecutionLog
from app.schemas.agent_log import AgentExecutionLogRead, AgentFeedbackCreate

router = APIRouter(prefix="/agent-runs", tags=["agents"])


@router.post("/{run_id}/feedback", response_model=AgentExecutionLogRead)
async def give_feedback(
    run_id: uuid.UUID, body: AgentFeedbackCreate, user: CurrentUser, session: SessionDep
) -> AgentExecutionLogRead:
    """👍/👎 from alpha-testers on a single agent output."""
    log = await session.get(AgentExecutionLog, run_id)
    if log is None or log.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent run not found")
    log.feedback = body.feedback
    log.feedback_comment = body.comment
    session.add(log)
    await session.commit()
    await session.refresh(log)
    return AgentExecutionLogRead.model_validate(log)
