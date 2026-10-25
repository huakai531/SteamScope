"""Bounded candidate selection; authorization happens before evidence and scores."""

from datetime import timedelta
from uuid import UUID

from sqlalchemy import Select, and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from steamscope_social.core.config import Settings
from steamscope_social.core.database import utcnow
from steamscope_social.modules.auth.models import SteamAccount
from steamscope_social.modules.players.service import Projection, project
from steamscope_social.modules.privacy.models import PrivacySettings
from steamscope_social.modules.social.models import Connection, UserBlock
from steamscope_social.modules.social.schemas import DiscoveryList, Person, Recommendation
from steamscope_social.modules.steam.models import SteamFriend, SyncState
from steamscope_social.modules.users.models import User


def candidates(viewer: UUID) -> Select[User]:
    connected = exists(
        select(Connection.user_id_low).where(
            or_(
                and_(Connection.user_id_low == viewer, Connection.user_id_high == User.id),
                and_(Connection.user_id_high == viewer, Connection.user_id_low == User.id),
            )
        )
    )
    blocked = exists(
        select(UserBlock.blocker_id).where(
            or_(
                and_(UserBlock.blocker_id == viewer, UserBlock.blocked_id == User.id),
                and_(UserBlock.blocker_id == User.id, UserBlock.blocked_id == viewer),
            )
        )
    )
    return (
        select(User)
        .join(SteamAccount, SteamAccount.user_id == User.id)
        .join(PrivacySettings, PrivacySettings.user_id == User.id)
        .where(
            User.id != viewer,
            User.status == "active",
            SteamAccount.verified_at.is_not(None),
            PrivacySettings.discovery.is_(True),
            ~blocked,
            or_(
                PrivacySettings.profile == "public",
                and_(PrivacySettings.profile == "connections", connected),
            ),
        )
    )


async def friend_ids(db: AsyncSession, viewer: UUID) -> set[str]:
    state = await db.get(SyncState, (viewer, "friends"))
    if (
        not state
        or not state.exposed
        or not state.snapshot_id
        or state.status not in {"populated", "empty"}
        or not state.last_success_at
        or state.last_success_at <= utcnow() - timedelta(seconds=900)
    ):
        return set()
    return set(
        await db.scalars(select(SteamFriend.friend_steam_id64).where(SteamFriend.user_id == viewer))
    )


def rank(left: Projection, right: Projection, steam_friend: bool) -> Recommendation:
    # Owner historical data can be displayed in Phase 4, but not advertised as a
    # current discovery signal. Unknown/private values never contribute points.
    available = (
        left.profile.library_state.data_available
        and not left.profile.library_state.stale
        and right.profile.library_state.data_available
        and not right.profile.library_state.stale
    )
    left_ids = {g.app_id for g in left.games}
    common = {g.app_id: g for g in right.games if g.app_id in left_ids} if available else {}
    recent_left = {
        g.app_id
        for g in left.profile.recent_games
        if g.recent_minutes is not None and g.recent_minutes > 0
    }
    recent_right = {
        g.app_id
        for g in right.profile.recent_games
        if g.recent_minutes is not None and g.recent_minutes > 0
    }
    recent = recent_left & recent_right & common.keys()
    similar = [
        a
        for a in left.games
        if a.app_id in common
        and a.total_minutes is not None
        and common[a.app_id].total_minutes is not None
        and a.total_minutes > 0
        and (b := common[a.app_id].total_minutes) is not None
        and b > 0
        and min(a.total_minutes, b) * 2 >= max(a.total_minutes, b)
    ]
    score = (
        min(len(common), 5) * 10
        + min(len(recent), 3) * 10
        + min(len(similar), 2) * 5
        + (10 if steam_friend else 0)
    )
    reasons = []
    if common:
        reasons.append(f"You both have {len(common)} visible games")
    if recent:
        reasons.append(f"You both recently played {len(recent)} visible games")
    if similar:
        reasons.append(f"Similar known playtime in {len(similar)} mutual games")
    if steam_friend:
        reasons.append("Your Steam friend is also on SteamScope")
    return Recommendation(
        person=Person(
            handle=right.profile.handle,
            display_name=right.profile.display_name,
            avatar_url=right.profile.avatar_url,
        ),
        score=score,
        mutual_games=len(common) if available else None,
        recent_overlap=len(recent)
        if available
        and left.profile.recent_state.data_available
        and right.profile.recent_state.data_available
        else None,
        reasons=reasons,
        steam_friend=steam_friend,
    )


async def discover(
    db: AsyncSession, viewer: UUID, config: Settings, *, only_friends: bool = False
) -> DiscoveryList:
    own = await db.get(User, viewer)
    assert own is not None
    left = await project(db, viewer, own.handle, config)
    friends = await friend_ids(db, viewer)
    if only_friends and not friends:
        return DiscoveryList(items=[])
    query = candidates(viewer)
    if only_friends:
        query = query.where(SteamAccount.steam_id.in_(friends))
    users = await db.scalars(query.order_by(func.lower(User.handle)).limit(60))
    result = []
    for user in users:
        linked = await db.scalar(
            select(SteamAccount.steam_id).where(SteamAccount.user_id == user.id)
        )
        right = await project(db, viewer, user.handle, config)
        item = rank(left, right, linked in friends)
        if item.score > 0:
            result.append(item)
    result.sort(key=lambda r: (-r.score, r.person.handle.lower()))
    return DiscoveryList(items=result[:20])
