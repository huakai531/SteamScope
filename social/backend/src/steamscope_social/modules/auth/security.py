import hashlib
import hmac
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from typing import cast

from fastapi import Request, Response
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from steamscope_social.core.config import Settings
from steamscope_social.core.database import utcnow
from steamscope_social.core.resources import Resources
from steamscope_social.modules.auth.models import UserSession
from steamscope_social.modules.auth.openid import TOKEN
from steamscope_social.modules.users.models import User


class AuthError(Exception):
    def __init__(self, status: int, code: str) -> None:
        self.status, self.code = status, code


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_token(token: str) -> str:
    return hmac.new(token.encode(), b"steamscope-csrf-v1", hashlib.sha256).hexdigest()


def config_for(request: Request) -> Settings:
    return cast(Settings, request.app.state.config)


def resources_for(request: Request) -> Resources:
    return cast(Resources, request.app.state.resources)


def session_cookie(config: Settings) -> str:
    return "__Host-steamscope_session" if config.cookie_secure else "steamscope_session"


def attempt_cookie(config: Settings, state: str) -> str:
    return ("__Secure-" if config.cookie_secure else "") + "ss_login_" + state[:16]


def get_cookie(request: Request, name: str) -> str:
    # Reject ambiguous duplicate credential cookies instead of relying on parser order.
    entries = request.headers.get("cookie", "").split(";")
    if sum(part.strip().split("=", 1)[0] == name for part in entries) > 1:
        raise AuthError(401, "AUTH_REQUIRED")
    value = request.cookies.get(name, "")
    return value if TOKEN.fullmatch(value) else ""


def set_session(response: Response, config: Settings, token: str) -> None:
    response.set_cookie(
        session_cookie(config),
        token,
        max_age=config.session_absolute_seconds,
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session(response: Response, config: Settings) -> None:
    response.delete_cookie(
        session_cookie(config), path="/", httponly=True, secure=config.cookie_secure, samesite="lax"
    )


RATE_SCRIPT = """
local n = redis.call('INCR', KEYS[1])
if n == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return n
"""


async def rate_limit(request: Request, group: str, identity: str, limit: int, seconds: int) -> None:
    config = config_for(request)
    key = config.redis_prefix + "rate:" + group + ":" + digest(identity)
    try:
        count = await resources_for(request).redis.eval(RATE_SCRIPT, 1, key, seconds)
    except (RedisError, TimeoutError):
        raise AuthError(503, "AUTH_DEPENDENCY_UNAVAILABLE") from None
    if int(count) > limit:
        raise AuthError(429, "RATE_LIMITED")


@dataclass
class Actor:
    user: User
    session: UserSession
    db: AsyncSession
    token: str = field(repr=False)


async def resolve_actor(db: AsyncSession, token: str, config: Settings) -> Actor:
    if not token:
        raise AuthError(401, "AUTH_REQUIRED")
    candidate = await db.scalar(
        select(UserSession).where(UserSession.token_digest == digest(token))
    )
    if candidate is None:
        raise AuthError(401, "AUTH_REQUIRED")
    user = await db.scalar(select(User).where(User.id == candidate.user_id).with_for_update())
    session = await db.scalar(
        select(UserSession)
        .where(UserSession.id == candidate.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    now = utcnow()
    if (
        user is None
        or user.status != "active"
        or session is None
        or session.revoked_at is not None
        or session.expires_at <= now
        or session.last_seen_at <= now - timedelta(seconds=config.session_idle_seconds)
    ):
        raise AuthError(401, "AUTH_REQUIRED")
    session.last_seen_at = now
    return Actor(user, session, db, token)


@asynccontextmanager
async def authenticated(request: Request, *, write: bool = False) -> AsyncIterator[Actor]:
    config = config_for(request)
    token = get_cookie(request, session_cookie(config))
    async with resources_for(request).sessions() as db, db.begin():
        actor = await resolve_actor(db, token, config)
        if write:
            if request.headers.get("origin") != config.browser_origin:
                raise AuthError(403, "ORIGIN_REJECTED")
            supplied = request.headers.get("x-csrf-token", "")
            if len(supplied) != 64 or not hmac.compare_digest(supplied, csrf_token(token)):
                raise AuthError(403, "CSRF_REJECTED")
            await rate_limit(
                request, "sensitive", str(actor.user.id), config.sensitive_rate_limit, 60
            )
        yield actor
