"""Read-time authorization precedes projection, filtering and aggregation.

No Redis results, provider clients or stored comparison state. Each projection uses
one repeatable-read snapshot after session validation, then revalidates that session
inside the snapshot. Revocations/privacy changes take effect on the next request.
"""

import base64
import hashlib
import json
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import Request
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from steamscope_social.core.config import Settings
from steamscope_social.core.database import utcnow
from steamscope_social.modules.auth.models import SteamAccount, UserSession
from steamscope_social.modules.auth.security import (
    AuthError,
    authenticated,
    config_for,
    resources_for,
)
from steamscope_social.modules.players.schemas import (
    MutualGame,
    PlayerComparison,
    PlayerGame,
    PlayerProfile,
    PlayerProgress,
    PlayerState,
)
from steamscope_social.modules.privacy.models import PrivacySettings
from steamscope_social.modules.social.policy import access
from steamscope_social.modules.steam.models import (
    AchievementDefinition,
    AchievementSchema,
    AchievementState,
    Game,
    RecentGame,
    SyncJob,
    SyncState,
    UserAchievement,
    UserGame,
)
from steamscope_social.modules.steam.schemas import AchievementView
from steamscope_social.modules.users.models import User


@asynccontextmanager
async def player_reader(request: Request) -> AsyncIterator[tuple[AsyncSession, UUID, Settings]]:
    config = config_for(request)
    # Preserve the established credential checks and normal session activity update.
    async with authenticated(request) as actor:
        owner, session_id = actor.user.id, actor.session.id
    async with resources_for(request).sessions() as db, db.begin():
        await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        now = utcnow()
        valid = await db.scalar(
            select(UserSession.id)
            .join(User, User.id == UserSession.user_id)
            .where(
                UserSession.id == session_id,
                User.id == owner,
                User.status == "active",
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
                UserSession.last_seen_at > now - timedelta(seconds=config.session_idle_seconds),
            )
        )
        if valid is None:
            raise AuthError(401, "AUTH_REQUIRED")
        yield db, owner, config


def source_state(
    row: SyncState | AchievementState | None,
    *,
    allowed: bool,
    owner: bool,
    now: datetime,
    ttl: int,
    hide_stale: bool = False,
    in_progress: bool = False,
) -> PlayerState:
    if not allowed:
        return PlayerState(status="private")
    if row is None:
        return PlayerState(status="never", in_progress=in_progress if owner else False)
    stale = bool(
        row.last_success_at
        and (
            (now - row.last_success_at).total_seconds() >= ttl
            or row.status not in {"populated", "empty", "partial"}
        )
    )
    visible = bool(row.exposed and row.snapshot_id and (not stale or (owner and not hide_stale)))
    return PlayerState(
        status=row.status,
        data_available=visible,
        stale=stale,
        last_success_at=row.last_success_at if owner or visible else None,
        in_progress=in_progress if owner else False,
    )


def total(values: Sequence[int | None]) -> int | None:
    return sum(v for v in values if v is not None) if all(v is not None for v in values) else None


@dataclass
class Projection:
    user_id: UUID
    viewer_id: UUID
    profile: PlayerProfile
    games: list[PlayerGame] = field(default_factory=list)
    items: dict[int, list[AchievementView]] = field(default_factory=dict)


async def project(db: AsyncSession, viewer: UUID, handle: str, config: Settings) -> Projection:
    record = (
        await db.execute(
            select(User, SteamAccount, PrivacySettings)
            .join(SteamAccount, SteamAccount.user_id == User.id)
            .join(PrivacySettings, PrivacySettings.user_id == User.id)
            .where(
                func.lower(User.handle) == handle.lower(),
                User.status == "active",
                SteamAccount.verified_at.is_not(None),
            )
        )
    ).one_or_none()
    if record is None:
        raise AuthError(404, "PLAYER_NOT_AVAILABLE")
    user, link, privacy = record
    owner = user.id == viewer
    relationship = await access(db, viewer, user.id)

    def permit(resource: str) -> bool:
        return relationship.permits(getattr(privacy, resource))

    if not permit("profile"):
        raise AuthError(404, "PLAYER_NOT_AVAILABLE")
    now = utcnow()
    states = {
        s.resource: s
        for s in await db.scalars(select(SyncState).where(SyncState.user_id == user.id))
    }
    active = {
        (scope, app_id)
        for scope, app_id in (
            (
                await db.execute(
                    select(SyncJob.scope, SyncJob.app_id).where(
                        SyncJob.user_id == user.id,
                        SyncJob.status.in_(("queued", "running", "retry")),
                    )
                )
            ).all()
            if owner
            else []
        )
    }
    lib = source_state(
        states.get("library"),
        allowed=permit("library"),
        owner=owner,
        now=now,
        ttl=21600,
        in_progress=("base", 0) in active,
    )
    persona = source_state(
        states.get("profile"),
        allowed=True,
        owner=owner,
        now=now,
        ttl=900,
        in_progress=("base", 0) in active,
    )
    playtime = permit("playtime") and lib.data_available
    achievements = permit("achievements") and lib.data_available
    recent = source_state(
        states.get("recent"),
        allowed=playtime,
        owner=owner,
        now=now,
        ttl=900,
        hide_stale=True,
        in_progress=("base", 0) in active,
    )
    profile = PlayerProfile(
        handle=user.handle,
        display_name=user.display_name,
        biography=user.biography,
        is_owner=owner,
        locale=user.locale if owner else None,
        timezone=user.timezone if owner else None,
        persona_name=link.persona_name if persona.data_available else None,
        steam_profile_url=link.profile_url if persona.data_available else None,
        profile_state=persona,
        library_state=lib,
        playtime_visible=playtime,
        achievements_visible=achievements,
        recent_state=recent,
    )
    projection = Projection(user.id, viewer, profile)
    if not lib.data_available:
        return projection
    rows = (
        await db.execute(select(UserGame, Game).join(Game).where(UserGame.user_id == user.id))
    ).all()
    astates = (
        {
            s.app_id: s
            for s in await db.scalars(
                select(AchievementState).where(AchievementState.user_id == user.id)
            )
        }
        if achievements
        else {}
    )
    schemas = (
        {
            s.app_id: s
            for s in await db.scalars(
                select(AchievementSchema).where(
                    AchievementSchema.app_id.in_(astates), AchievementSchema.language == "english"
                )
            )
        }
        if astates
        else {}
    )
    definitions: dict[int, dict[str, AchievementDefinition]] = {}
    players: dict[int, dict[str, UserAchievement]] = {}
    if astates:
        for d in await db.scalars(
            select(AchievementDefinition).where(
                AchievementDefinition.app_id.in_(astates),
                AchievementDefinition.language == "english",
            )
        ):
            definitions.setdefault(d.app_id, {})[d.api_name] = d
        for p in await db.scalars(
            select(UserAchievement).where(UserAchievement.user_id == user.id)
        ):
            players.setdefault(p.app_id, {})[p.api_name] = p
    recent_fresh = bool(
        states.get("library")
        and states["library"].last_success_at
        and (now - states["library"].last_success_at).total_seconds() < 900
    )
    for row, game in rows:
        state = source_state(
            astates.get(row.app_id),
            allowed=achievements,
            owner=owner,
            now=now,
            ttl=900,
            in_progress=("achievements", row.app_id) in active,
        )
        progress = PlayerProgress(state=state)
        # Definitions are not returned through this player's route when progress is hidden.
        if state.data_available:
            schema = schemas.get(row.app_id)
            defs = definitions.get(row.app_id, {})
            personal = players.get(row.app_id, {})
            current = bool(
                schema
                and schema.revision
                and schema.status in {"populated", "empty"}
                and schema.last_success_at
                and (now - schema.last_success_at).total_seconds() < config.steam_schema_ttl_seconds
            )
            compatible = bool(
                schema
                and schema.revision
                and astates[row.app_id].schema_revision == schema.revision
                and defs.keys() == personal.keys()
                and all(p.unlocked is not None for p in personal.values())
            )
            progress.coverage = "partial"
            progress.definition_count = len(defs) if schema and schema.revision else None
            progress.known_unlocked = sum(p.unlocked is True for p in personal.values())
            progress.known_locked = sum(p.unlocked is False for p in personal.values())
            if compatible:
                progress.coverage = (
                    ("complete" if defs else "no_achievements")
                    if current and not state.stale
                    else "stale"
                )
                if progress.coverage == "complete":
                    progress.completion_percent = round(
                        100 * progress.known_unlocked / len(defs), 2
                    )
            projection.items[row.app_id] = [
                AchievementView(
                    api_name=n,
                    display_name=defs[n].display_name if n in defs else None,
                    description=defs[n].description if n in defs else None,
                    hidden=defs[n].hidden if n in defs else True,
                    definition_available=n in defs,
                    unlocked=personal[n].unlocked if n in personal else None,
                    unlocked_at=personal[n].unlocked_at if n in personal else None,
                )
                for n in sorted(set(defs) | set(personal))
            ]
        projection.games.append(
            PlayerGame(
                app_id=row.app_id,
                name=game.name,
                total_minutes=row.total_minutes if playtime else None,
                recent_minutes=row.recent_minutes if playtime and recent_fresh else None,
                last_played_at=row.last_played_at if playtime else None,
                achievements=progress,
            )
        )
    projection.games.sort(key=lambda g: g.app_id)
    profile.game_count = len(projection.games)
    profile.total_minutes = total([g.total_minutes for g in projection.games]) if playtime else None
    profile.synchronized_achievement_games = (
        sum(g.achievements.state.data_available for g in projection.games) if achievements else None
    )
    profile.most_played = (
        sorted(
            [g for g in projection.games if g.total_minutes is not None],
            key=lambda g: (-(g.total_minutes or 0), g.app_id),
        )[:5]
        if playtime
        else []
    )
    if recent.data_available:
        recent_rows = (
            await db.execute(
                select(RecentGame, Game).join(Game).where(RecentGame.user_id == user.id)
            )
        ).all()
        library = {g.app_id: g for g in projection.games}
        profile.recent_games = [
            library[r.app_id].model_copy(update={"recent_minutes": r.recent_minutes})
            for r, _ in sorted(
                recent_rows,
                key=lambda pair: (
                    pair[0].recent_minutes is None,
                    -(pair[0].recent_minutes or 0),
                    pair[0].app_id,
                ),
            )
            if r.app_id in library
        ][:5]
    return projection


def paginate[T: BaseModel](
    rows: list[T], context: object, cursor: str | None, limit: int
) -> tuple[list[T], str | None]:
    revision = hashlib.sha256(
        json.dumps(
            [context, [r.model_dump(mode="json") for r in rows]], sort_keys=True, default=str
        ).encode()
    ).hexdigest()
    offset = 0
    if cursor:
        try:
            value = json.loads(base64.urlsafe_b64decode(cursor.encode()))
            if (
                not isinstance(value, list)
                or len(value) != 2
                or type(value[1]) is not int
                or not 0 <= value[1] <= 20000
            ):
                raise ValueError
            if value[0] != revision:
                raise AuthError(409, "PLAYER_SNAPSHOT_CHANGED")
            offset = value[1]
        except (ValueError, UnicodeError, TypeError):
            raise AuthError(422, "INVALID_REQUEST") from None
    following = (
        base64.urlsafe_b64encode(json.dumps([revision, offset + limit]).encode()).decode()
        if offset + limit < len(rows)
        else None
    )
    return rows[offset : offset + limit], following


def comparison(left: Projection, right: Projection) -> PlayerComparison:
    lp, rp = left.profile, right.profile
    visible = lp.library_state.data_available and rp.library_state.data_available
    view = PlayerComparison(
        left_handle=lp.handle,
        right_handle=rp.handle,
        status="available" if visible else "unavailable",
        left_library_state=lp.library_state,
        right_library_state=rp.library_state,
        items=[],
    )
    if not visible:
        return view
    right_games = {g.app_id: g for g in right.games}
    for a in left.games:
        b = right_games.get(a.app_id)
        if b is None:
            continue
        comparable = a.achievements.coverage == b.achievements.coverage == "complete"
        # Same shared English schema is read in this transaction; complete coverage binds revisions.
        view.items.append(
            MutualGame(
                app_id=a.app_id,
                name=a.name,
                left_minutes=a.total_minutes,
                right_minutes=b.total_minutes,
                difference_minutes=a.total_minutes - b.total_minutes
                if a.total_minutes is not None and b.total_minutes is not None
                else None,
                left_recent_minutes=a.recent_minutes
                if a.recent_minutes is not None and b.recent_minutes is not None
                else None,
                right_recent_minutes=b.recent_minutes
                if a.recent_minutes is not None and b.recent_minutes is not None
                else None,
                left_achievements=a.achievements.model_copy(update={"completion_percent": None}),
                right_achievements=b.achievements.model_copy(update={"completion_percent": None}),
                left_completion=a.achievements.completion_percent if comparable else None,
                right_completion=b.achievements.completion_percent if comparable else None,
            )
        )
    view.mutual_count = len(view.items)
    view.left_total_minutes = (
        total([g.left_minutes for g in view.items]) if lp.playtime_visible else None
    )
    view.right_total_minutes = (
        total([g.right_minutes for g in view.items]) if rp.playtime_visible else None
    )
    view.comparable_achievement_games = (
        sum(g.left_completion is not None and g.right_completion is not None for g in view.items)
        if lp.achievements_visible and rp.achievements_visible
        else None
    )
    return view
