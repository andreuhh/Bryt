from fastapi import HTTPException, status

from app.agents.context import MissingProfileError
from app.agents.llm import AgentError, AgentRefusalError, AgentUnavailableError
from app.agents.training_periodization import NoActivePlanError


def agent_http_error(exc: Exception) -> HTTPException:
    """Maps agent-layer failures to HTTP. Details are already persisted in AgentExecutionLog."""
    if isinstance(exc, MissingProfileError):
        return HTTPException(status.HTTP_409_CONFLICT, "Complete onboarding first")
    if isinstance(exc, NoActivePlanError):
        return HTTPException(status.HTTP_409_CONFLICT, "No active training plan")
    if isinstance(exc, AgentUnavailableError):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    if isinstance(exc, AgentRefusalError):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))
    if isinstance(exc, AgentError):
        return HTTPException(status.HTTP_502_BAD_GATEWAY, f"Agent failed: {exc}")
    raise exc
