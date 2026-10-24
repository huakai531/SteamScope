"""Run explicitly: python -m steamscope_social.modules.administration.cleanup.

Expire attempts/credentials and 90-day minimal audits; no business job handler.
"""

import asyncio
from datetime import timedelta

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from steamscope_social.core.config import Settings
from steamscope_social.core.database import utcnow
from steamscope_social.core.models import AuditLog, LoginAttempt, UserSession
from steamscope_social.core.resources import Resources
from steamscope_social.modules.chat.models import Message, MessageReport
from steamscope_social.modules.social.models import (
    ConnectionRequest,
    SocialNotification,
    UserReport,
)


async def purge_expired(db: AsyncSession, config: Settings) -> None:
    now = utcnow()
    await db.execute(delete(LoginAttempt).where(LoginAttempt.expires_at <= now))
    await db.execute(
        delete(UserSession).where(
            (UserSession.expires_at <= now)
            | UserSession.revoked_at.is_not(None)
            | (UserSession.last_seen_at <= now - timedelta(seconds=config.session_idle_seconds))
        )
    )
    await db.execute(delete(AuditLog).where(AuditLog.created_at < now - timedelta(days=90)))
    await db.execute(delete(UserReport).where(UserReport.expires_at <= now))
    await db.execute(delete(MessageReport).where(MessageReport.expires_at <= now))
    await db.execute(
        update(Message)
        .where(Message.deleted_at < now - timedelta(days=90), Message.body != "")
        .values(body="")
    )
    await db.execute(
        delete(SocialNotification).where(SocialNotification.created_at < now - timedelta(days=90))
    )
    await db.execute(
        delete(ConnectionRequest).where(ConnectionRequest.created_at < now - timedelta(days=90))
    )


async def main() -> None:
    config = Settings()
    resources = Resources(config)
    try:
        async with resources.sessions() as db, db.begin():
            await purge_expired(db, config)
        print("Expired credentials, audits and retained social history removed")
    finally:
        await resources.close()


if __name__ == "__main__":
    asyncio.run(main())
