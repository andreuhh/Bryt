from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.agents.coach_chat import ChatQuotaExceededError, chat, chat_quota
from app.agents.context import MissingProfileError
from app.agents.llm import AgentError, LLMClient, get_llm
from app.api.deps import CurrentUser, SessionDep
from app.api.errors import agent_http_error
from app.schemas.coach import ChatQuota, ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])


@router.get("/chat/quota", response_model=ChatQuota)
async def get_chat_quota(user: CurrentUser, session: SessionDep) -> ChatQuota:
    return await chat_quota(session, user)


@router.post("/chat", response_model=ChatResponse)
async def coach_chat(
    body: ChatRequest,
    user: CurrentUser,
    session: SessionDep,
    llm: Annotated[LLMClient, Depends(get_llm)],
) -> ChatResponse:
    if body.messages[-1].role != "user":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Last message must be from the user"
        )
    try:
        output, log = await chat(session, llm, user, body.messages)
    except ChatQuotaExceededError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from exc
    except (AgentError, MissingProfileError) as exc:
        raise agent_http_error(exc) from exc
    return ChatResponse(
        reply=output.reply,
        proposed_adjustment=output.proposed_adjustment,
        agent_run_id=log.id,
        quota=await chat_quota(session, user),
    )
