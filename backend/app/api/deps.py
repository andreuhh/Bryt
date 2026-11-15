"""Shared FastAPI dependencies: DB session and authenticated user (tenant)."""

import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import AuthenticatedPrincipal, AuthError, verify_supabase_token
from app.core.config import get_settings
from app.core.database import get_session
from app.models import User

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_bearer = HTTPBearer(auto_error=False)


async def get_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    x_dev_user_id: Annotated[str | None, Header()] = None,
) -> AuthenticatedPrincipal:
    settings = get_settings()
    if credentials is not None:
        try:
            return await verify_supabase_token(credentials.credentials, settings)
        except AuthError as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    if x_dev_user_id and settings.is_development:
        try:
            user_id = uuid.UUID(x_dev_user_id)
        except ValueError as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid X-Dev-User-Id") from exc
        return AuthenticatedPrincipal(user_id=user_id, email=f"{user_id}@dev.bryt.local")
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")


async def get_current_user(
    principal: Annotated[AuthenticatedPrincipal, Depends(get_principal)],
    session: SessionDep,
) -> User:
    """Returns the tenant row, provisioning it on first request after Supabase sign-up."""
    user = await session.get(User, principal.user_id)
    if user is None:
        user = User(id=principal.user_id, email=principal.email or f"{principal.user_id}@unknown")
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
