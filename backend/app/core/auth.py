"""Supabase Auth JWT verification.

- Production: `Authorization: Bearer <supabase access token>`, verified against the project's
  JWKS (asymmetric signing keys) or, for legacy projects, the shared HS256 secret.
- Development only (ENVIRONMENT=development): `X-Dev-User-Id: <uuid>` bypasses Supabase so
  endpoints can be exercised from Swagger / curl before the Supabase project exists.
"""

import asyncio
import uuid
from dataclasses import dataclass
from functools import lru_cache

import jwt

from app.core.config import Settings


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    user_id: uuid.UUID
    email: str | None


@lru_cache
def _jwks_client(jwks_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)


async def verify_supabase_token(token: str, settings: Settings) -> AuthenticatedPrincipal:
    try:
        alg = jwt.get_unverified_header(token).get("alg")
        if alg == "HS256":
            if not settings.supabase_jwt_secret:
                raise AuthError("HS256 tokens not accepted: SUPABASE_JWT_SECRET not configured")
            key: object = settings.supabase_jwt_secret
        else:
            if not settings.supabase_url:
                raise AuthError("Supabase not configured: set SUPABASE_URL")
            jwks_url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
            # PyJWKClient does blocking HTTP on cache miss: keep it off the event loop
            signing_key = await asyncio.to_thread(
                _jwks_client(jwks_url).get_signing_key_from_jwt, token
            )
            key = signing_key.key

        claims = jwt.decode(
            token,
            key,  # type: ignore[arg-type]
            algorithms=["HS256", "RS256", "ES256"],
            audience=settings.supabase_jwt_audience,
            options={"require": ["sub", "exp"]},
        )
        return AuthenticatedPrincipal(user_id=uuid.UUID(claims["sub"]), email=claims.get("email"))
    except AuthError:
        raise
    except (jwt.PyJWTError, ValueError) as exc:
        raise AuthError(f"Invalid token: {exc}") from exc
