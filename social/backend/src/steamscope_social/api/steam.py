from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import func, select

from steamscope_social.api.errors import ErrorResponse
from steamscope_social.core.database import utcnow
from steamscope_social.modules.administration.models import AuditLog
from steamscope_social.modules.auth.models import SteamAccount
from steamscope_social.modules.auth.security import Actor, AuthError, authenticated, config_for
from steamscope_social.modules.steam.client import RESOURCES, Resource, capability
from steamscope_social.modules.steam.jobs import ACTIVE, clear_imported, enqueue
from steamscope_social.modules.steam.models import (
    Game,
    RecentGame,
    SyncJob,
    SyncRun,
    SyncState,
    UserGame,
)
from steamscope_social.modules.steam.schemas import (
    ClearSteamData,
    EnqueuedView,
    GamesView,
    GameView,
    JobDetail,
    JobView,
    ResourceView,
    RunView,
    SteamProfileView,
    SyncStatusView,
)
from steamscope_social.modules.steam.visuals import game_visual

router = APIRouter(
    prefix="/api/v1/me/steam",
    tags=["Owner Steam data"],
    responses={status: {"model": ErrorResponse} for status in (401, 403, 404, 409, 422, 429, 503)},
)


async def resource_view(actor: Actor, resource: Resource) -> ResourceView:
    row = await actor.db.get(SyncState, (actor.user.id, resource))
    active = await actor.db.scalar(
        select(SyncJob).where(
            SyncJob.user_id == actor.user.id,
            SyncJob.scope == ("friends" if resource == "friends" else "base"),
            SyncJob.status.in_(ACTIVE),
        )
    )
    progress = active is not None and active.outcomes.get(resource) in {None, "retry"}
    if row is None:
        return ResourceView(
            resource=resource, status="never", code="NEVER_SYNCED", in_progress=progress
        )
    age = (utcnow() - row.last_success_at).total_seconds() if row.last_success_at else None
    stale = age is not None and (
        age >= (21600 if resource == "library" else 900) or row.status not in {"empty", "populated"}
    )
    visible = row.exposed and row.snapshot_id is not None
    # Recent activity is a captured two-week window, not a perpetual live statistic.
    if resource in {"recent", "friends"} and age is not None and age >= 900:
        visible = False
    return ResourceView(
        resource=resource,
        status=row.status,
        code=row.code,
        last_attempt_at=row.last_attempt_at,
        last_success_at=row.last_success_at,
        snapshot_id=row.snapshot_id if visible else None,
        stale=stale,
        in_progress=progress,
        data_available=visible,
    )


@router.post(
    "/sync",
    response_model=EnqueuedView,
    status_code=202,
    responses={200: {"model": EnqueuedView, "description": "Active compatible job reused"}},
)
async def sync(request: Request, response: Response) -> EnqueuedView:
    """Enqueue only. 202 new job; 200 reuses active job; 429 cooldown, no implicit GET sync."""
    async with authenticated(request, write=True) as actor:
        job, reused = await enqueue(actor.db, actor.user, config_for(request))
        response.status_code = 200 if reused else 202
        return EnqueuedView(job=JobView.model_validate(job), reused=reused)


@router.get("/sync-status", response_model=SyncStatusView)
async def sync_status(request: Request) -> SyncStatusView:
    async with authenticated(request) as actor:
        config = config_for(request)
        ready = capability(config)
        latest = await actor.db.scalar(
            select(SyncJob)
            .where(SyncJob.user_id == actor.user.id, SyncJob.scope == "base")
            .order_by(SyncJob.created_at.desc())
            .limit(1)
        )
        return SyncStatusView(
            capability=ready,
            operator_instruction=None
            if ready == "configured"
            else (
                "Steam sync not configured. The project owner must privately configure "
                "SOCIAL_STEAM_API_KEY on the API and worker, then recreate those containers. "
                "Do not send a key in chat."
            ),
            resources=[await resource_view(actor, resource) for resource in RESOURCES],
            latest_job=JobView.model_validate(latest) if latest else None,
            cooldown_until=latest.created_at + timedelta(seconds=config.steam_sync_cooldown_seconds)
            if latest
            else None,
        )


@router.get("/sync-jobs/{job_id}", response_model=JobDetail)
async def job_detail(request: Request, job_id: UUID) -> JobDetail:
    async with authenticated(request) as actor:
        job = await actor.db.scalar(
            select(SyncJob).where(SyncJob.id == job_id, SyncJob.user_id == actor.user.id)
        )
        if job is None:
            raise AuthError(404, "SYNC_JOB_NOT_FOUND")
        runs = (
            await actor.db.scalars(
                select(SyncRun).where(SyncRun.job_id == job.id).order_by(SyncRun.attempt)
            )
        ).all()
        return JobDetail(
            job=JobView.model_validate(job), runs=[RunView.model_validate(run) for run in runs]
        )


@router.get("/profile", response_model=SteamProfileView)
async def profile(request: Request) -> SteamProfileView:
    async with authenticated(request) as actor:
        state = await resource_view(actor, "profile")
        link = await actor.db.scalar(
            select(SteamAccount).where(SteamAccount.user_id == actor.user.id)
        )
        assert link is not None
        return SteamProfileView(
            state=state,
            persona_name=link.persona_name if state.data_available else None,
            profile_url=link.profile_url if state.data_available else None,
            avatar_url=link.avatar_url if state.data_available else None,
            source_visibility=link.source_visibility if state.data_available else None,
        )


@router.get("/games", response_model=GamesView)
async def games(
    request: Request,
    after: int = Query(default=0, ge=0, le=4294967295),
    limit: int = Query(default=25, ge=1, le=100),
    snapshot: UUID | None = None,
) -> GamesView:
    """Keyset app-ID pagination. Send snapshot on later pages; 409 means restart pagination."""
    async with authenticated(request) as actor:
        state = await resource_view(actor, "library")
        if not state.data_available:
            return GamesView(state=state, items=[])
        if (after and snapshot is None) or (snapshot and snapshot != state.snapshot_id):
            raise AuthError(409, "STEAM_SNAPSHOT_CHANGED")
        rows = (
            await actor.db.execute(
                select(UserGame, Game)
                .join(Game, Game.app_id == UserGame.app_id)
                .where(UserGame.user_id == actor.user.id, UserGame.app_id > after)
                .order_by(UserGame.app_id)
                .limit(limit + 1)
            )
        ).all()
        count, known, total = (
            await actor.db.execute(
                select(
                    func.count(),
                    func.count(UserGame.total_minutes),
                    func.sum(UserGame.total_minutes),
                ).where(UserGame.user_id == actor.user.id)
            )
        ).one()
        recent_valid = (
            state.last_success_at is not None
            and state.last_success_at > utcnow() - timedelta(minutes=15)
        )
        return GamesView(
            state=state,
            items=[
                GameView(
                    app_id=row.app_id,
                    name=game.name,
                    visual=game_visual(game.app_id, game.icon_hash),
                    total_minutes=row.total_minutes,
                    recent_minutes=row.recent_minutes if recent_valid else None,
                    last_played_at=row.last_played_at,
                )
                for row, game in rows[:limit]
            ],
            next_after=rows[limit - 1][0].app_id if len(rows) > limit else None,
            returned_game_count=count,
            total_minutes=(total or 0) if count == known else None,
        )


@router.get("/recent-games", response_model=GamesView)
async def recent_games(request: Request) -> GamesView:
    async with authenticated(request) as actor:
        state = await resource_view(actor, "recent")
        if not state.data_available:
            return GamesView(state=state, items=[])
        rows = (
            await actor.db.execute(
                select(RecentGame, Game)
                .join(Game, Game.app_id == RecentGame.app_id)
                .where(RecentGame.user_id == actor.user.id)
                .order_by(RecentGame.app_id)
            )
        ).all()
        return GamesView(
            state=state,
            items=[
                GameView(
                    app_id=row.app_id,
                    name=game.name,
                    visual=game_visual(game.app_id, game.icon_hash),
                    total_minutes=row.total_minutes,
                    recent_minutes=row.recent_minutes,
                )
                for row, game in rows
            ],
            returned_game_count=len(rows),
            window_end=state.last_success_at,
            window_start=state.last_success_at - timedelta(days=14)
            if state.last_success_at
            else None,
        )


@router.delete("/data", status_code=204)
async def clear_data(request: Request, body: ClearSteamData) -> Response:
    """Confirmed clear; preserves login and settings, fences queued/in-flight work."""
    async with authenticated(request, write=True) as actor:
        if actor.session.authenticated_at < utcnow() - timedelta(
            seconds=config_for(request).recent_auth_seconds
        ):
            raise AuthError(403, "REAUTH_REQUIRED")
        await clear_imported(actor.db, actor.user)
        actor.db.add(AuditLog(actor_id=actor.user.id, event="steam_data_cleared"))
    return Response(status_code=204)
