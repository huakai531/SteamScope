import secrets
from datetime import timedelta

from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from steamscope_social.core.config import Settings
from steamscope_social.core.database import utcnow
from steamscope_social.modules.administration.models import AuditLog
from steamscope_social.modules.auth.models import LoginAttempt, SteamAccount, UserSession
from steamscope_social.modules.auth.security import AuthError, digest, new_token
from steamscope_social.modules.privacy.models import PrivacySettings
from steamscope_social.modules.users.models import User


def initial_handle() -> str:
    return "player_" + secrets.token_hex(6)


async def find_or_create_user(db: AsyncSession, steam_id: str) -> User:
    # Serialize only this verified identity; uniqueness also protects writes outside this code.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"), {"identity": steam_id}
    )
    link = await db.scalar(select(SteamAccount).where(SteamAccount.steam_id == steam_id))
    if link:
        user = await db.scalar(select(User).where(User.id == link.user_id).with_for_update())
        if user is None or user.status != "active":
            raise AuthError(403, "ACCOUNT_UNAVAILABLE")
        return user
    for _ in range(5):
        try:
            async with db.begin_nested():
                user = User(handle=initial_handle(), display_name="New player")
                db.add(user)
                await db.flush()
                db.add_all(
                    [
                        SteamAccount(user_id=user.id, steam_id=steam_id),
                        PrivacySettings(user_id=user.id),
                    ]
                )
                await db.flush()
            db.add(AuditLog(actor_id=user.id, event="account_created"))
            return user
        except IntegrityError:
            continue
    raise AuthError(503, "ACCOUNT_CREATION_UNAVAILABLE")


async def issue_session(db: AsyncSession, user: User, config: Settings) -> str:
    now = utcnow()
    # Bounded active session list; invalidated credentials fail on their next request.
    active = list(
        (
            await db.scalars(
                select(UserSession)
                .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
                .order_by(UserSession.created_at.desc())
            )
        ).all()
    )
    for previous in active[19:]:
        previous.revoked_at = now
    token = new_token()
    db.add(
        UserSession(
            user_id=user.id,
            token_digest=digest(token),
            expires_at=now + timedelta(seconds=config.session_absolute_seconds),
        )
    )
    db.add(AuditLog(actor_id=user.id, event="session_issued"))
    await db.flush()
    return token


async def finish_login(
    db: AsyncSession, attempt: LoginAttempt, steam_id: str, config: Settings
) -> str:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"), {"identity": steam_id}
    )
    if attempt.bound_user_id is not None:
        bound = await db.scalar(
            select(User).where(User.id == attempt.bound_user_id).with_for_update()
        )
        previous = await db.get(UserSession, attempt.bound_session_id)
        if (
            bound is None
            or bound.status != "active"
            or previous is None
            or previous.revoked_at is not None
            or previous.expires_at <= utcnow()
            or previous.last_seen_at <= utcnow() - timedelta(seconds=config.session_idle_seconds)
        ):
            raise AuthError(401, "LOGIN_BINDING_EXPIRED")
        if attempt.purpose == "reauth":
            link = await db.scalar(select(SteamAccount).where(SteamAccount.user_id == bound.id))
            if link is None or link.steam_id != steam_id:
                raise AuthError(403, "REAUTH_IDENTITY_MISMATCH")
            previous.revoked_at = utcnow()
            db.add(AuditLog(actor_id=bound.id, event="reauthenticated"))
            return await issue_session(db, bound, config)
        previous.revoked_at = utcnow()
    user = await find_or_create_user(db, steam_id)
    return await issue_session(db, user, config)


async def revoke_session(db: AsyncSession, session: UserSession) -> None:
    session.revoked_at = utcnow()
    await db.execute(delete(LoginAttempt).where(LoginAttempt.bound_session_id == session.id))


async def revoke_all(db: AsyncSession, user: User) -> None:
    await db.execute(
        update(UserSession).where(UserSession.user_id == user.id).values(revoked_at=utcnow())
    )
    await db.execute(delete(LoginAttempt).where(LoginAttempt.bound_user_id == user.id))
