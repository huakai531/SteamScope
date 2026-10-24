"""Owner-only saved achievements and imported Steam edges; GET never schedules work."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request, Response
from sqlalchemy import func, select

from steamscope_social.api.errors import ErrorResponse
from steamscope_social.api.steam import resource_view
from steamscope_social.core.database import utcnow
from steamscope_social.modules.auth.security import Actor, AuthError, authenticated, config_for
from steamscope_social.modules.steam.jobs import ACTIVE, enqueue
from steamscope_social.modules.steam.models import (
    AchievementDefinition,
    AchievementSchema,
    AchievementState,
    SteamFriend,
    SyncJob,
    UserAchievement,
)
from steamscope_social.modules.steam.repository import eligible, schema_fresh
from steamscope_social.modules.steam.schemas import (
    AchievementsView,
    AchievementView,
    EnqueuedView,
    FriendsView,
    FriendView,
    JobView,
    ResourceView,
    SchemaView,
)

router = APIRouter(
    prefix="/api/v1/me/steam",
    tags=["Owner Steam data"],
    responses={s: {"model": ErrorResponse} for s in (401, 403, 404, 409, 422, 429, 503)},
)


async def latest_job(actor: Actor, scope: str, app_id: int = 0) -> SyncJob | None:
    return await actor.db.scalar(
        select(SyncJob)
        .where(SyncJob.user_id == actor.user.id, SyncJob.scope == scope, SyncJob.app_id == app_id)
        .order_by(SyncJob.created_at.desc())
        .limit(1)
    )


@router.post(
    "/games/{appid}/achievements/sync",
    response_model=EnqueuedView,
    status_code=202,
    responses={200: {"model": EnqueuedView}},
)
async def sync_achievements(
    request: Request, response: Response, appid: int = Path(ge=1, le=4294967295)
) -> EnqueuedView:
    async with authenticated(request, write=True) as actor:
        job, reused = await enqueue(
            actor.db, actor.user, config_for(request), "achievements", appid
        )
        response.status_code = 200 if reused else 202
        return EnqueuedView(job=JobView.model_validate(job), reused=reused)


@router.post(
    "/friends/sync",
    response_model=EnqueuedView,
    status_code=202,
    responses={200: {"model": EnqueuedView}},
)
async def sync_friends(request: Request, response: Response) -> EnqueuedView:
    async with authenticated(request, write=True) as actor:
        job, reused = await enqueue(actor.db, actor.user, config_for(request), "friends")
        response.status_code = 200 if reused else 202
        return EnqueuedView(job=JobView.model_validate(job), reused=reused)


@router.get("/friends", response_model=FriendsView)
async def friends(
    request: Request,
    after: str = Query(default="", pattern=r"^(|[0-9]{17})$"),
    limit: int = Query(default=25, ge=1, le=100),
    snapshot: UUID | None = None,
) -> FriendsView:
    async with authenticated(request) as actor:
        state = await resource_view(actor, "friends")
        job = await latest_job(actor, "friends")
        view = JobView.model_validate(job) if job else None
        if not state.data_available:
            return FriendsView(state=state, latest_job=view, total_count=None, items=[])
        if (after and snapshot is None) or (snapshot and snapshot != state.snapshot_id):
            raise AuthError(409, "STEAM_SNAPSHOT_CHANGED")
        rows = list(
            await actor.db.scalars(
                select(SteamFriend)
                .where(SteamFriend.user_id == actor.user.id, SteamFriend.friend_steam_id64 > after)
                .order_by(SteamFriend.friend_steam_id64)
                .limit(limit + 1)
            )
        )
        total = await actor.db.scalar(
            select(func.count())
            .select_from(SteamFriend)
            .where(SteamFriend.user_id == actor.user.id)
        )
        return FriendsView(
            state=state,
            latest_job=view,
            total_count=total,
            items=[
                FriendView(
                    steam_id64=row.friend_steam_id64,
                    profile_url=f"https://steamcommunity.com/profiles/{row.friend_steam_id64}/",
                    friend_since=row.friend_since,
                )
                for row in rows[:limit]
            ],
            next_after=rows[limit - 1].friend_steam_id64 if len(rows) > limit else None,
        )


@router.get("/games/{appid}/achievements", response_model=AchievementsView)
async def achievements(
    request: Request,
    appid: int = Path(ge=1, le=4294967295),
    after: str = Query(default="", max_length=128),
    limit: int = Query(default=50, ge=1, le=100),
    snapshot: UUID | None = None,
    revision: str | None = Query(default=None, pattern=r"^[a-f0-9]{64}$"),
) -> AchievementsView:
    async with authenticated(request) as actor:
        if not await eligible(actor.db, actor.user.id, appid):
            raise AuthError(404, "STEAM_GAME_NOT_ELIGIBLE")
        row = await actor.db.get(AchievementState, (actor.user.id, appid))
        # Keep metadata and definitions in one short consistent read; no HTTP under this lock.
        schema = await actor.db.scalar(
            select(AchievementSchema)
            .where(AchievementSchema.app_id == appid, AchievementSchema.language == "english")
            .with_for_update()
        )
        now = utcnow()
        fresh_schema = bool(schema and schema_fresh(schema, now, config_for(request)))
        job = await latest_job(actor, "achievements", appid)
        progress = bool(job and job.status in ACTIVE)
        state = ResourceView(
            resource="achievements", status="never", code="NEVER_SYNCED", in_progress=progress
        )
        if row:
            state = ResourceView(
                resource="achievements",
                status=row.status,
                code=row.code,
                last_attempt_at=row.last_attempt_at,
                last_success_at=row.last_success_at,
                snapshot_id=row.snapshot_id if row.exposed else None,
                data_available=bool(row.exposed and row.snapshot_id),
                in_progress=progress,
                stale=bool(
                    row.last_success_at
                    and (
                        (now - row.last_success_at).total_seconds() >= 900
                        or row.status not in {"populated", "empty", "partial"}
                    )
                ),
            )
        schema_view = SchemaView(
            status=schema.status if schema else "never",
            code=schema.code if schema else "NEVER_SYNCED",
            revision=schema.revision if schema else None,
            last_success_at=schema.last_success_at if schema else None,
            stale=bool(schema and schema.revision and not fresh_schema),
        )
        if (
            (after and (snapshot is None or revision is None))
            or (snapshot and snapshot != state.snapshot_id)
            or (revision and revision != schema_view.revision)
        ):
            raise AuthError(409, "STEAM_SNAPSHOT_CHANGED")
        definitions = {
            d.api_name: d
            for d in await actor.db.scalars(
                select(AchievementDefinition).where(
                    AchievementDefinition.app_id == appid,
                    AchievementDefinition.language == "english",
                )
            )
        }
        player = (
            {
                p.api_name: p
                for p in await actor.db.scalars(
                    select(UserAchievement).where(
                        UserAchievement.user_id == actor.user.id, UserAchievement.app_id == appid
                    )
                )
            }
            if state.data_available
            else {}
        )
        known_unlocked = (
            sum(p.unlocked is True for p in player.values()) if state.data_available else None
        )
        known_locked = (
            sum(p.unlocked is False for p in player.values()) if state.data_available else None
        )
        denominator = len(definitions) if schema and schema.revision else None
        compatible = bool(
            row
            and schema
            and row.schema_revision
            and row.schema_revision == schema.revision
            and definitions.keys() == player.keys()
            and all(p.unlocked is not None for p in player.values())
        )
        coverage: Literal["unknown", "complete", "partial", "no_achievements", "stale"] = "unknown"
        percent = None
        if state.data_available:
            coverage = "partial"
            if compatible and fresh_schema and not state.stale:
                coverage = "complete" if denominator else "no_achievements"
                percent = (
                    round(100 * (known_unlocked or 0) / denominator, 2) if denominator else None
                )
            elif compatible and (state.stale or not fresh_schema):
                coverage = "stale"
        names = sorted(set(definitions) | set(player))
        page = [name for name in names if name > after][: limit + 1]
        items = []
        for name in page[:limit]:
            definition, personal = definitions.get(name), player.get(name)
            items.append(
                AchievementView(
                    api_name=name,
                    display_name=definition.display_name if definition else None,
                    description=definition.description if definition else None,
                    hidden=definition.hidden if definition else True,
                    definition_available=definition is not None,
                    unlocked=personal.unlocked if personal else None,
                    unlocked_at=personal.unlocked_at if personal else None,
                )
            )
        return AchievementsView(
            app_id=appid,
            state=state,
            schema_state=schema_view,
            latest_job=JobView.model_validate(job) if job else None,
            coverage=coverage,
            known_unlocked=known_unlocked,
            known_locked=known_locked,
            definition_count=denominator,
            completion_percent=percent,
            items=items,
            next_after=page[limit - 1] if len(page) > limit else None,
        )
