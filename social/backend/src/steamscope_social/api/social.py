from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request, Response
from sqlalchemy import delete, func, or_, select, update

from steamscope_social.api.errors import ErrorResponse
from steamscope_social.core.database import utcnow
from steamscope_social.modules.auth.security import AuthError, authenticated, rate_limit
from steamscope_social.modules.players.service import paginate, player_reader
from steamscope_social.modules.social.discovery import candidates, discover
from steamscope_social.modules.social.models import (
    Connection,
    ConnectionRequest,
    SocialNotification,
    UserBlock,
)
from steamscope_social.modules.social.policy import access
from steamscope_social.modules.social.schemas import (
    DiscoveryList,
    NotificationList,
    NotificationView,
    Person,
    PersonList,
    ReportInput,
    ReportReceipt,
    RequestList,
    RequestView,
    SocialRelationship,
    TargetInput,
)
from steamscope_social.modules.social.service import (
    block,
    mutation,
    relationship,
    remove_connection,
    report,
    request_view,
    send_request,
    transition,
    verified_user,
    visible_person,
)
from steamscope_social.modules.users.models import User

router = APIRouter(
    prefix="/api/v1",
    tags=["Social graph"],
    responses={s: {"model": ErrorResponse} for s in (401, 403, 404, 409, 422, 429, 503)},
)
Handle = Annotated[str, Path(pattern=r"^[A-Za-z][A-Za-z0-9_]{2,23}$")]
Cursor = Annotated[str | None, Query(max_length=180)]


@router.get("/users/search", response_model=PersonList)
async def search(request: Request, q: str = Query(min_length=3, max_length=64)) -> PersonList:
    if len(q.strip()) < 3:
        raise AuthError(422, "INVALID_REQUEST")
    async with player_reader(request) as (db, viewer, _):
        await rate_limit(request, "search", str(viewer), 30, 60)
        # Literal substring only. No SteamID lookup, wildcards, totals or cursors.
        needle = q.strip().lower()
        users = await db.scalars(
            candidates(viewer)
            .where(
                or_(
                    func.strpos(func.lower(User.handle), needle) > 0,
                    func.strpos(func.lower(User.display_name), needle) > 0,
                )
            )
            .order_by(func.lower(User.handle))
            .limit(20)
        )
        return PersonList(
            items=[Person(handle=u.handle, display_name=u.display_name) for u in users]
        )


@router.get("/discovery/players", response_model=DiscoveryList)
async def discovery(request: Request) -> DiscoveryList:
    async with player_reader(request) as (db, viewer, config):
        await rate_limit(request, "discovery", str(viewer), 15, 60)
        return await discover(db, viewer, config)


@router.get("/discovery/steam-friends", response_model=DiscoveryList)
async def steam_friends(request: Request) -> DiscoveryList:
    async with player_reader(request) as (db, viewer, config):
        await rate_limit(request, "discovery", str(viewer), 15, 60)
        return await discover(db, viewer, config, only_friends=True)


@router.get("/users/{handle}/relationship", response_model=SocialRelationship)
async def social_relationship(request: Request, handle: Handle) -> SocialRelationship:
    async with player_reader(request) as (db, viewer, _):
        await rate_limit(request, "social-read", str(viewer), 60, 60)
        return await relationship(db, viewer, await verified_user(db, handle))


@router.post("/connection-requests", response_model=RequestView)
async def send(request: Request, body: TargetInput) -> RequestView:
    async with mutation(request, handle=body.handle, group="requests") as (actor, target):
        return await send_request(actor, target)


async def request_list(request: Request, incoming: bool, cursor: str | None) -> RequestList:
    async with player_reader(request) as (db, viewer, _):
        await rate_limit(request, "social-read", str(viewer), 60, 60)
        rows = await db.scalars(
            select(ConnectionRequest)
            .where(
                (ConnectionRequest.receiver_id if incoming else ConnectionRequest.sender_id)
                == viewer,
                ConnectionRequest.status == "pending",
                ConnectionRequest.expires_at > utcnow(),
            )
            .order_by(ConnectionRequest.created_at.desc(), ConnectionRequest.id)
            .limit(1000)
        )
        views = []
        for r in rows:
            other = r.sender_id if incoming else r.receiver_id
            if not (await access(db, viewer, other)).blocked:
                views.append(await request_view(db, viewer, r))
        items, following = paginate(views, [viewer, incoming], cursor, 25)
        return RequestList(items=items, next_cursor=following)


@router.get("/connection-requests/incoming", response_model=RequestList)
async def incoming(request: Request, cursor: Cursor = None) -> RequestList:
    return await request_list(request, True, cursor)


@router.get("/connection-requests/outgoing", response_model=RequestList)
async def outgoing(request: Request, cursor: Cursor = None) -> RequestList:
    return await request_list(request, False, cursor)


@router.post("/connection-requests/{request_id}/accept", response_model=RequestView)
async def accept(request: Request, request_id: UUID) -> RequestView:
    async with mutation(request, request_id=request_id) as (actor, target):
        return await transition(actor, target, request_id, "accept")


@router.post("/connection-requests/{request_id}/reject", response_model=RequestView)
async def reject(request: Request, request_id: UUID) -> RequestView:
    async with mutation(request, request_id=request_id) as (actor, target):
        return await transition(actor, target, request_id, "reject")


@router.delete("/connection-requests/{request_id}", response_model=RequestView)
async def cancel(request: Request, request_id: UUID) -> RequestView:
    async with mutation(request, request_id=request_id) as (actor, target):
        return await transition(actor, target, request_id, "cancel")


@router.get("/connections", response_model=PersonList)
async def connections(request: Request, cursor: Cursor = None) -> PersonList:
    async with player_reader(request) as (db, viewer, _):
        await rate_limit(request, "social-read", str(viewer), 60, 60)
        rows = await db.scalars(
            select(Connection).where(
                or_(Connection.user_id_low == viewer, Connection.user_id_high == viewer)
            )
        )
        people = []
        for row in rows:
            other = row.user_id_high if row.user_id_low == viewer else row.user_id_low
            user = await db.get(User, other)
            if user and (person := await visible_person(db, viewer, user, directed_consent=True)):
                people.append(person)
        people.sort(key=lambda p: p.handle.lower())
        items, following = paginate(people, [viewer, "connections"], cursor, 25)
        return PersonList(items=items, next_cursor=following)


@router.delete("/connections/{handle}", status_code=204)
async def remove(request: Request, handle: Handle) -> Response:
    async with mutation(request, handle=handle) as (actor, target):
        policy = await access(actor.db, actor.user.id, target.id)
        if not policy.connected and await visible_person(actor.db, actor.user.id, target) is None:
            raise AuthError(404, "SOCIAL_UNAVAILABLE")
        await remove_connection(actor, target)
    return Response(status_code=204)


@router.post("/blocks/{handle}", status_code=204)
async def create_block(request: Request, handle: Handle) -> Response:
    async with mutation(request, handle=handle, group="blocks") as (actor, target):
        await block(actor, target)
    return Response(status_code=204)


@router.delete("/blocks/{handle}", status_code=204)
async def unblock(request: Request, handle: Handle) -> Response:
    async with mutation(request, handle=handle, group="blocks") as (actor, target):
        if (
            await actor.db.get(UserBlock, (actor.user.id, target.id)) is None
            and await visible_person(actor.db, actor.user.id, target) is None
        ):
            raise AuthError(404, "SOCIAL_UNAVAILABLE")
        await actor.db.execute(
            delete(UserBlock).where(
                UserBlock.blocker_id == actor.user.id, UserBlock.blocked_id == target.id
            )
        )
    return Response(status_code=204)


@router.get("/blocks", response_model=PersonList)
async def blocks(request: Request, cursor: Cursor = None) -> PersonList:
    async with player_reader(request) as (db, viewer, _):
        await rate_limit(request, "social-read", str(viewer), 60, 60)
        # Owner manages their explicit directional block, not reverse block status.
        users = await db.scalars(
            select(User)
            .join(UserBlock, UserBlock.blocked_id == User.id)
            .where(UserBlock.blocker_id == viewer)
            .order_by(func.lower(User.handle))
        )
        items, following = paginate(
            [Person(handle=u.handle, display_name=u.display_name) for u in users],
            [viewer, "blocks"],
            cursor,
            25,
        )
        return PersonList(items=items, next_cursor=following)


@router.post("/reports", response_model=ReportReceipt)
async def create_report(request: Request, body: ReportInput) -> ReportReceipt:
    async with mutation(request, handle=body.handle, group="reports") as (actor, target):
        return await report(actor, target, body)


@router.get("/notifications", response_model=NotificationList)
async def notifications(request: Request, cursor: Cursor = None) -> NotificationList:
    async with player_reader(request) as (db, viewer, _):
        await rate_limit(request, "social-read", str(viewer), 60, 60)
        rows = await db.scalars(
            select(SocialNotification)
            .where(SocialNotification.recipient_id == viewer)
            .order_by(SocialNotification.created_at.desc(), SocialNotification.id)
            .limit(1000)
        )
        views = []
        for row in rows:
            user = await db.get(User, row.actor_id)
            if not user or (await access(db, viewer, user.id)).blocked:
                continue
            related = await db.get(ConnectionRequest, row.request_id)
            active = (
                related is not None
                and related.status == "pending"
                and related.expires_at > utcnow()
            )
            person = await visible_person(db, viewer, user, directed_consent=active)
            views.append(
                NotificationView(
                    id=row.id,
                    kind=row.kind,
                    person=person,
                    request_id=row.request_id,
                    created_at=row.created_at,
                    read_at=row.read_at,
                )
            )
        items, following = paginate(views, [viewer, "notifications"], cursor, 25)
        return NotificationList(items=items, next_cursor=following)


@router.post("/notifications/read-all", status_code=204)
async def read_all(request: Request) -> Response:
    async with authenticated(request, write=True) as actor:
        await actor.db.execute(
            update(SocialNotification)
            .where(
                SocialNotification.recipient_id == actor.user.id,
                SocialNotification.read_at.is_(None),
            )
            .values(read_at=utcnow())
        )
    return Response(status_code=204)


@router.post("/notifications/{notification_id}/read", status_code=204)
async def read_notification(request: Request, notification_id: UUID) -> Response:
    async with authenticated(request, write=True) as actor:
        row = await actor.db.scalar(
            select(SocialNotification).where(
                SocialNotification.id == notification_id,
                SocialNotification.recipient_id == actor.user.id,
            )
        )
        if row is None:
            raise AuthError(404, "SOCIAL_UNAVAILABLE")
        row.read_at = row.read_at or utcnow()
    return Response(status_code=204)
