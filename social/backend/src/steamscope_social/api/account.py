from datetime import datetime, timedelta
from typing import Literal, cast
from uuid import UUID

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from redis.exceptions import RedisError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from steamscope_social.api.errors import ErrorResponse
from steamscope_social.core.database import utcnow
from steamscope_social.modules.administration.models import AuditLog
from steamscope_social.modules.auth.models import LoginAttempt, SteamAccount, UserSession
from steamscope_social.modules.auth.openid import (
    OpenIDRejected,
    authentication_url,
    callback_parameters,
    verify_assertion,
)
from steamscope_social.modules.auth.security import (
    Actor,
    AuthError,
    attempt_cookie,
    authenticated,
    clear_session,
    config_for,
    csrf_token,
    digest,
    get_cookie,
    new_token,
    rate_limit,
    resolve_actor,
    resources_for,
    session_cookie,
    set_session,
)
from steamscope_social.modules.auth.service import finish_login, revoke_all, revoke_session
from steamscope_social.modules.privacy.models import PrivacySettings
from steamscope_social.modules.privacy.schemas import PrivacyView
from steamscope_social.modules.steam.jobs import clear_imported
from steamscope_social.modules.steam.models import SyncState
from steamscope_social.modules.users.schemas import AccountView, DeleteAccount, ProfileUpdate

router = APIRouter(
    prefix="/api/v1",
    tags=["Account and authentication"],
    responses={
        status: {"model": ErrorResponse, "description": description}
        for status, description in {
            401: "Missing, expired or revoked session",
            403: "Origin, CSRF, status or recent identity rejected",
            404: "Owned resource not found",
            409: "Case-insensitive handle conflict",
            422: "Invalid or server-controlled fields",
            429: "Redis-backed rate limit; Retry-After",
            503: "Required service unavailable; authentication fails closed",
        }.items()
    },
)
DESTINATIONS = {
    "/account",
    "/account/profile",
    "/account/privacy",
    "/account/sessions",
    "/account/delete",
    "/account/steam",
}


class CSRFView(BaseModel):
    csrf_token: str


class LoginView(BaseModel):
    url: str


class SessionView(BaseModel):
    id: UUID
    created_at: datetime
    authenticated_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    current: bool


async def account_view(actor: Actor) -> AccountView:
    link = await actor.db.scalar(select(SteamAccount).where(SteamAccount.user_id == actor.user.id))
    if link is None:
        raise AuthError(403, "ACCOUNT_UNAVAILABLE")
    user = actor.user
    states = (
        await actor.db.scalars(
            select(SyncState).where(
                SyncState.user_id == user.id,
                SyncState.resource.in_(("profile", "library", "recent")),
            )
        )
    ).all()
    synchronized = len(states) == 3 and all(
        state.status in {"empty", "populated"}
        and state.exposed
        and state.last_success_at is not None
        and state.last_success_at
        > utcnow() - timedelta(seconds=21600 if state.resource == "library" else 900)
        for state in states
    )
    return AccountView(
        id=user.id,
        handle=user.handle,
        display_name=user.display_name,
        biography=user.biography,
        locale=user.locale,
        timezone=user.timezone,
        steam_id=link.steam_id,
        created_at=user.created_at,
        steam_data_synchronized=synchronized,
    )


async def prepare_attempt(
    request: Request,
    purpose: Literal["login", "reauth"],
    destination: str,
    actor: Actor | None = None,
) -> tuple[str, str]:
    config = config_for(request)
    if destination not in DESTINATIONS:
        raise AuthError(422, "INVALID_DESTINATION")
    await rate_limit(
        request,
        "login",
        request.client.host if request.client else "unknown",
        config.auth_rate_limit,
        300,
    )
    state, browser = new_token(), new_token()
    attempt = LoginAttempt(
        state_digest=digest(state),
        browser_digest=digest(browser),
        purpose=purpose,
        destination=destination,
        expires_at=utcnow() + timedelta(seconds=config.login_attempt_seconds),
    )
    if actor:
        attempt.bound_user_id, attempt.bound_session_id = actor.user.id, actor.session.id
        actor.db.add(attempt)
    else:
        async with resources_for(request).sessions() as db, db.begin():
            token = get_cookie(request, session_cookie(config))
            if token:
                try:
                    existing = await resolve_actor(db, token, config)
                    attempt.bound_user_id, attempt.bound_session_id = (
                        existing.user.id,
                        existing.session.id,
                    )
                except AuthError as error:
                    if error.status != 401:
                        raise
            db.add(attempt)
    return state, browser


def bind_cookie(request: Request, response: Response, state: str, browser: str) -> None:
    config = config_for(request)
    response.set_cookie(
        attempt_cookie(config, state),
        browser,
        max_age=config.login_attempt_seconds,
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
        path="/api/v1/auth/steam/callback",
    )


@router.get("/auth/steam/login", response_class=RedirectResponse, status_code=303)
async def login(request: Request, next: str = "/account") -> Response:
    """Start browser-bound OpenID login. Only allowlisted local next routes are accepted."""
    config = config_for(request)
    if request.headers.get("sec-fetch-site") == "cross-site" or request.headers.get(
        "origin"
    ) not in {None, config.browser_origin}:
        raise AuthError(403, "ORIGIN_REJECTED")
    state, browser = await prepare_attempt(request, "login", next)
    response = RedirectResponse(authentication_url(config, state), status_code=303)
    bind_cookie(request, response, state, browser)
    return response


@router.post("/auth/steam/reauth", response_model=LoginView)
async def reauthenticate(
    request: Request, response: Response, next: str = "/account/delete"
) -> LoginView:
    """Session + CSRF + exact Origin. Reverification does not force a Steam password prompt."""
    async with authenticated(request, write=True) as actor:
        state, browser = await prepare_attempt(request, "reauth", next, actor)
        bind_cookie(request, response, state, browser)
        return LoginView(url=authentication_url(config_for(request), state))


@router.get("/auth/steam/callback", response_class=RedirectResponse, status_code=303)
async def callback(request: Request) -> Response:
    """Consume a browser-bound attempt, discover identity and verify with Steam before writes."""
    config, resources = config_for(request), resources_for(request)
    state = ""
    try:
        params = callback_parameters(list(request.query_params.multi_items()))
        state = params["state"]
        browser = get_cookie(request, attempt_cookie(config, state))
        if not browser:
            raise OpenIDRejected()
        await rate_limit(
            request,
            "callback",
            request.client.host if request.client else "unknown",
            config.auth_rate_limit,
            300,
        )
        # DELETE ... RETURNING consumes only the matching browser's attempt atomically.
        async with resources.sessions() as db, db.begin():
            attempt = await db.scalar(
                delete(LoginAttempt)
                .where(
                    LoginAttempt.state_digest == digest(state),
                    LoginAttempt.browser_digest == digest(browser),
                    LoginAttempt.expires_at > utcnow(),
                )
                .returning(LoginAttempt)
            )
        if attempt is None:
            raise OpenIDRejected()
        if params.get("openid.mode") == "cancel":
            raise AuthError(400, "LOGIN_CANCELLED")
        steam_id, nonce = await verify_assertion(
            params, config, cast(httpx.AsyncClient, request.app.state.openid_client)
        )
        try:
            fresh = await resources.redis.set(
                config.redis_prefix + "nonce:" + digest(nonce), "1", nx=True, ex=660
            )
        except (RedisError, TimeoutError):
            raise AuthError(503, "AUTH_DEPENDENCY_UNAVAILABLE") from None
        if not fresh:
            raise OpenIDRejected()
        async with resources.sessions() as db, db.begin():
            token = await finish_login(db, attempt, steam_id, config)
        response: Response = RedirectResponse(
            config.browser_origin + attempt.destination, status_code=303
        )
        set_session(response, config, token)
    except (OpenIDRejected, AuthError) as error:
        code = error.code if isinstance(error, AuthError) else "LOGIN_FAILED"
        response = RedirectResponse(config.browser_origin + "/login?error=" + code, status_code=303)
    if state:
        response.delete_cookie(
            attempt_cookie(config, state),
            path="/api/v1/auth/steam/callback",
            httponly=True,
            secure=config.cookie_secure,
            samesite="lax",
        )
    return response


@router.get("/auth/csrf", response_model=CSRFView)
async def csrf(request: Request) -> CSRFView:
    """Authenticated, uncached synchronizer token; keep in memory, never localStorage."""
    async with authenticated(request) as actor:
        return CSRFView(csrf_token=csrf_token(actor.token))


@router.get("/me", response_model=AccountView)
async def me(request: Request) -> AccountView:
    async with authenticated(request) as actor:
        return await account_view(actor)


@router.patch("/me", response_model=AccountView)
async def update_profile(request: Request, body: ProfileUpdate) -> AccountView:
    """Owner only; exact Origin and CSRF. Unknown/server-controlled fields return 422."""
    try:
        async with authenticated(request, write=True) as actor:
            for key, value in body.model_dump(exclude_unset=True).items():
                setattr(actor.user, key, value)
            actor.user.updated_at = utcnow()
            actor.db.add(AuditLog(actor_id=actor.user.id, event="profile_updated"))
            await actor.db.flush()
            return await account_view(actor)
    except IntegrityError:
        raise AuthError(409, "HANDLE_UNAVAILABLE") from None


@router.get("/me/privacy", response_model=PrivacyView)
async def privacy(request: Request) -> PrivacyView:
    async with authenticated(request) as actor:
        return PrivacyView.model_validate(await actor.db.get(PrivacySettings, actor.user.id))


@router.patch("/me/privacy", response_model=PrivacyView)
async def update_privacy(request: Request, body: PrivacyView) -> PrivacyView:
    async with authenticated(request, write=True) as actor:
        current = await actor.db.get(PrivacySettings, actor.user.id)
        for key, value in body.model_dump(exclude_unset=True).items():
            setattr(current, key, value)
        actor.db.add(AuditLog(actor_id=actor.user.id, event="privacy_updated"))
        await actor.db.flush()
        return PrivacyView.model_validate(current)


@router.get("/me/sessions", response_model=list[SessionView])
async def sessions(request: Request) -> list[SessionView]:
    async with authenticated(request) as actor:
        rows = (
            await actor.db.scalars(
                select(UserSession)
                .where(
                    UserSession.user_id == actor.user.id,
                    UserSession.revoked_at.is_(None),
                    UserSession.expires_at > utcnow(),
                    UserSession.last_seen_at
                    > utcnow() - timedelta(seconds=config_for(request).session_idle_seconds),
                )
                .order_by(UserSession.created_at.desc())
                .limit(20)
            )
        ).all()
        return [
            SessionView(
                id=row.id,
                created_at=row.created_at,
                authenticated_at=row.authenticated_at,
                last_seen_at=row.last_seen_at,
                expires_at=row.expires_at,
                current=row.id == actor.session.id,
            )
            for row in rows
        ]


@router.delete("/me/sessions/{session_id}", status_code=204)
async def revoke(request: Request, session_id: UUID) -> Response:
    async with authenticated(request, write=True) as actor:
        target = await actor.db.scalar(
            select(UserSession).where(
                UserSession.id == session_id, UserSession.user_id == actor.user.id
            )
        )
        if target is None:
            raise AuthError(404, "SESSION_NOT_FOUND")
        await revoke_session(actor.db, target)
        actor.db.add(AuditLog(actor_id=actor.user.id, event="session_revoked"))
        response = Response(status_code=204)
        if target.id == actor.session.id:
            clear_session(response, config_for(request))
        return response


@router.post("/auth/logout", status_code=204)
async def logout(request: Request) -> Response:
    async with authenticated(request, write=True) as actor:
        await revoke_session(actor.db, actor.session)
        actor.db.add(AuditLog(actor_id=actor.user.id, event="logged_out"))
    response = Response(status_code=204)
    clear_session(response, config_for(request))
    return response


@router.post("/auth/logout-all", status_code=204)
async def logout_all(request: Request) -> Response:
    async with authenticated(request, write=True) as actor:
        await revoke_all(actor.db, actor.user)
        actor.db.add(AuditLog(actor_id=actor.user.id, event="logged_out_all"))
    response = Response(status_code=204)
    clear_session(response, config_for(request))
    return response


@router.delete("/me", status_code=204)
async def delete_account(request: Request, body: DeleteAccount) -> Response:
    """Atomic account/import erasure and job fencing; confirmation and recent verification."""
    async with authenticated(request, write=True) as actor:
        if actor.session.authenticated_at < utcnow() - timedelta(
            seconds=config_for(request).recent_auth_seconds
        ):
            raise AuthError(403, "REAUTH_REQUIRED")
        await clear_imported(actor.db, actor.user, deleting=True)
        # FKs atomically erase linkage, settings, credentials and account-bound attempts.
        await actor.db.delete(actor.user)
        await actor.db.flush()
        actor.db.add(AuditLog(actor_id=None, event="account_deleted"))
    response = Response(status_code=204)
    clear_session(response, config_for(request))
    return response
