"""Shared current relationship policy used before all player/social projections."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from steamscope_social.modules.social.models import Connection, UserBlock


def pair(a: UUID, b: UUID) -> tuple[UUID, UUID]:
    return (a, b) if a.int < b.int else (b, a)


@dataclass(frozen=True)
class Access:
    owner: bool
    connected: bool = False
    blocked: bool = False

    def permits(self, visibility: str) -> bool:
        return self.owner or (
            not self.blocked
            and (visibility == "public" or (visibility == "connections" and self.connected))
        )


async def access(db: AsyncSession, viewer: UUID, target: UUID) -> Access:
    if viewer == target:
        return Access(owner=True)
    blocked = await db.scalar(
        select(UserBlock.blocker_id)
        .where(
            or_(
                and_(UserBlock.blocker_id == viewer, UserBlock.blocked_id == target),
                and_(UserBlock.blocker_id == target, UserBlock.blocked_id == viewer),
            )
        )
        .limit(1)
    )
    low, high = pair(viewer, target)
    connected = await db.get(Connection, (low, high)) if blocked is None else None
    return Access(owner=False, connected=connected is not None, blocked=blocked is not None)
