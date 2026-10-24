from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query, Request
from sqlalchemy import select

from steamscope_social.api.errors import ErrorResponse
from steamscope_social.modules.auth.security import AuthError
from steamscope_social.modules.players.schemas import (
    PlayerAchievements,
    PlayerComparison,
    PlayerGameDetail,
    PlayerLibrary,
    PlayerProfile,
)
from steamscope_social.modules.players.service import comparison, paginate, player_reader, project
from steamscope_social.modules.users.models import User

router = APIRouter(
    prefix="/api/v1/users",
    tags=["Player profiles"],
    responses={s: {"model": ErrorResponse} for s in (401, 404, 409, 422, 503)},
)
Handle = Annotated[str, Path(pattern=r"^[A-Za-z][A-Za-z0-9_]{2,23}$")]
AppID = Annotated[int, Path(ge=1, le=4294967295)]
Cursor = Annotated[str | None, Query(max_length=180)]
Limit = Annotated[int, Query(ge=1, le=100)]
Sort = Literal["name", "total", "recent", "last_played"]


@router.get("/{handle}", response_model=PlayerProfile)
async def profile(request: Request, handle: Handle) -> PlayerProfile:
    async with player_reader(request) as (db, viewer, config):
        return (await project(db, viewer, handle, config)).profile


@router.get("/{handle}/games", response_model=PlayerLibrary)
async def games(
    request: Request,
    handle: Handle,
    q: str = Query(default="", max_length=80),
    sort: Sort = "name",
    achievements: bool = False,
    recent: bool = False,
    cursor: Cursor = None,
    limit: Limit = 25,
) -> PlayerLibrary:
    async with player_reader(request) as (db, viewer, config):
        p = await project(db, viewer, handle, config)
        state = p.profile.library_state
        result = PlayerLibrary(
            state=state,
            playtime_visible=p.profile.playtime_visible,
            achievements_visible=p.profile.achievements_visible,
            items=[],
        )
        if not state.data_available:
            return result
        if ((sort != "name" or recent) and not p.profile.playtime_visible) or (
            achievements and not p.profile.achievements_visible
        ):
            raise AuthError(422, "PLAYER_FILTER_UNAVAILABLE")
        rows = [
            g
            for g in p.games
            if q.casefold() in (g.name or "").casefold()
            and (not achievements or g.achievements.state.data_available)
            and (not recent or (g.recent_minutes is not None and g.recent_minutes > 0))
        ]
        if sort == "name":
            rows.sort(key=lambda g: (g.name is None, (g.name or "").casefold(), g.app_id))
        elif sort == "last_played":
            rows.sort(
                key=lambda g: (
                    g.last_played_at is None,
                    -(g.last_played_at.timestamp() if g.last_played_at else 0),
                    g.app_id,
                )
            )
        else:
            rows.sort(
                key=lambda g: (
                    getattr(g, sort + "_minutes") is None,
                    -(getattr(g, sort + "_minutes") or 0),
                    g.app_id,
                )
            )
        result.total_count = len(rows)
        result.items, result.next_cursor = paginate(
            rows, [viewer, p.user_id, q, sort, achievements, recent, state], cursor, limit
        )
        return result


@router.get("/{handle}/games/{appid}", response_model=PlayerGameDetail)
async def game(request: Request, handle: Handle, appid: AppID) -> PlayerGameDetail:
    async with player_reader(request) as (db, viewer, config):
        p = await project(db, viewer, handle, config)
        row = next((g for g in p.games if g.app_id == appid), None)
        if row is None:
            raise AuthError(404, "PLAYER_GAME_NOT_AVAILABLE")
        return PlayerGameDetail(
            handle=p.profile.handle,
            library_state=p.profile.library_state,
            playtime_visible=p.profile.playtime_visible,
            game=row,
        )


@router.get("/{handle}/games/{appid}/achievements", response_model=PlayerAchievements)
async def achievements(
    request: Request, handle: Handle, appid: AppID, cursor: Cursor = None, limit: Limit = 50
) -> PlayerAchievements:
    async with player_reader(request) as (db, viewer, config):
        p = await project(db, viewer, handle, config)
        row = next((g for g in p.games if g.app_id == appid), None)
        if row is None:
            raise AuthError(404, "PLAYER_GAME_NOT_AVAILABLE")
        items, following = paginate(
            p.items.get(appid, []), [viewer, p.user_id, appid, row.achievements], cursor, limit
        )
        return PlayerAchievements(
            app_id=appid, progress=row.achievements, items=items, next_cursor=following
        )


@router.get("/{handle}/comparison", response_model=PlayerComparison)
async def compare(
    request: Request, handle: Handle, cursor: Cursor = None, limit: Limit = 25
) -> PlayerComparison:
    async with player_reader(request) as (db, viewer, config):
        own = await db.scalar(select(User.handle).where(User.id == viewer))
        if own is None:
            raise AuthError(401, "AUTH_REQUIRED")
        left, right = (
            await project(db, viewer, own, config),
            await project(db, viewer, handle, config),
        )
        result = comparison(left, right)
        result.items, result.next_cursor = paginate(
            result.items,
            [
                viewer,
                left.user_id,
                right.user_id,
                result.left_library_state,
                result.right_library_state,
            ],
            cursor,
            limit,
        )
        return result
