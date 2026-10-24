"""Transactional social actions. Pair writes lock both users in UUID order first."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID

from fastapi import Request
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from steamscope_social.core.database import utcnow
from steamscope_social.modules.auth.models import SteamAccount
from steamscope_social.modules.auth.security import (
    Actor,
    AuthError,
    authenticated,
    config_for,
    rate_limit,
    resolve_actor,
    resources_for,
)
from steamscope_social.modules.privacy.models import PrivacySettings
from steamscope_social.modules.social.models import (
    Connection,
    ConnectionRequest,
    SocialNotification,
    UserBlock,
    UserReport,
)
from steamscope_social.modules.social.policy import access, pair
from steamscope_social.modules.social.schemas import (
    Person,
    ReportInput,
    ReportReceipt,
    RequestView,
    SocialRelationship,
)
from steamscope_social.modules.users.models import User


async def verified_user(db: AsyncSession, handle: str) -> User:
    user = await db.scalar(
        select(User)
        .join(SteamAccount)
        .where(
            func.lower(User.handle) == handle.lower(),
            User.status == "active",
            SteamAccount.verified_at.is_not(None),
        )
    )
    if user is None:
        raise AuthError(404, "SOCIAL_UNAVAILABLE")
    return user


@asynccontextmanager
async def mutation(
    request: Request,
    *,
    handle: str | None = None,
    request_id: UUID | None = None,
    group: str = "social-actions",
) -> AsyncIterator[tuple[Actor, User]]:
    # Release the ordinary actor lock before acquiring the pair. A->B and B->A
    # must never each hold their own user lock while waiting for the other.
    async with authenticated(request, write=True) as initial:
        owner, token = initial.user.id, initial.token
        await rate_limit(
            request,
            group,
            str(owner),
            3 if group == "reports" else 10 if group == "requests" else 30,
            3600 if group == "reports" else 60,
        )
        if group == "requests":
            await rate_limit(request, "requests-day", str(owner), 50, 86400)
    async with resources_for(request).sessions() as db, db.begin():
        if request_id is not None:
            row = await db.get(ConnectionRequest, request_id)
            if row is None or owner not in {row.sender_id, row.receiver_id}:
                raise AuthError(404, "SOCIAL_UNAVAILABLE")
            target_id = row.receiver_id if row.sender_id == owner else row.sender_id
        else:
            assert handle is not None
            target_id = (await verified_user(db, handle)).id
        if target_id == owner:
            raise AuthError(422, "SOCIAL_SELF_ACTION")
        locked = list(
            await db.scalars(
                select(User.id)
                .where(User.id.in_(pair(owner, target_id)))
                .order_by(User.id)
                .with_for_update()
            )
        )
        if len(locked) != 2:
            raise AuthError(404, "SOCIAL_UNAVAILABLE")
        actor = await resolve_actor(db, token, config_for(request))
        target = await db.scalar(
            select(User)
            .join(SteamAccount)
            .where(
                User.id == target_id, User.status == "active", SteamAccount.verified_at.is_not(None)
            )
            .execution_options(populate_existing=True)
        )
        if target is None or (handle is not None and target.handle.lower() != handle.lower()):
            raise AuthError(404, "SOCIAL_UNAVAILABLE")
        yield actor, target


async def visible_person(
    db: AsyncSession, viewer: UUID, user: User, *, directed_consent: bool = False
) -> Person | None:
    policy = await access(db, viewer, user.id)
    settings = await db.get(PrivacySettings, user.id)
    linked = await db.scalar(
        select(SteamAccount.id).where(
            SteamAccount.user_id == user.id, SteamAccount.verified_at.is_not(None)
        )
    )
    if user.status != "active" or linked is None or settings is None or policy.blocked:
        return None
    if not directed_consent and not policy.permits(settings.profile):
        return None
    return Person(handle=user.handle, display_name=user.display_name)


async def eligible(db: AsyncSession, actor: UUID, target: User) -> bool:
    settings = await db.get(PrivacySettings, target.id)
    policy = await access(db, actor, target.id)
    return bool(
        not policy.owner
        and not policy.blocked
        and not policy.connected
        and settings
        and settings.discovery
        and settings.connection_requests == "discoverable"
        and policy.permits(settings.profile)
    )


async def pending(db: AsyncSession, a: UUID, b: UUID) -> ConnectionRequest | None:
    low, high = pair(a, b)
    return await db.scalar(
        select(ConnectionRequest).where(
            ConnectionRequest.user_id_low == low,
            ConnectionRequest.user_id_high == high,
            ConnectionRequest.status == "pending",
            ConnectionRequest.expires_at > utcnow(),
        )
    )


async def relationship(db: AsyncSession, actor: UUID, target: User) -> SocialRelationship:
    policy = await access(db, actor, target.id)
    if policy.owner:
        return SocialRelationship(status="self")
    if policy.blocked or await visible_person(db, actor, target) is None:
        raise AuthError(404, "SOCIAL_UNAVAILABLE")
    if policy.connected:
        return SocialRelationship(status="connected")
    row = await pending(db, actor, target.id)
    if row:
        return SocialRelationship(
            status="outgoing" if row.sender_id == actor else "incoming", request_id=row.id
        )
    return SocialRelationship(status="none", can_request=await eligible(db, actor, target))


async def request_view(db: AsyncSession, actor: UUID, row: ConnectionRequest) -> RequestView:
    incoming = actor == row.receiver_id
    user = await db.get(User, row.sender_id if incoming else row.receiver_id)
    status = "expired" if row.status == "pending" and row.expires_at <= utcnow() else row.status
    # Sending explicitly discloses only handle/name to the intended recipient.
    # It never grants profile, Steam or private resource access.
    person = (
        await visible_person(db, actor, user, directed_consent=status == "pending")
        if user
        else None
    )
    return RequestView(
        id=row.id,
        person=person,
        direction="incoming" if incoming else "outgoing",
        status=status,
        created_at=row.created_at,
        expires_at=row.expires_at,
    )


def notify(
    db: AsyncSession, row: ConnectionRequest, recipient: UUID, actor: UUID, kind: str
) -> None:
    # Called only at one locked state transition. DB unique event index is the
    # independent retry backstop. No name, SteamID, report text or profile payload.
    db.add(SocialNotification(recipient_id=recipient, actor_id=actor, request_id=row.id, kind=kind))


async def send_request(actor: Actor, target: User) -> RequestView:
    db, owner = actor.db, actor.user.id
    if not await eligible(db, owner, target):
        raise AuthError(404, "SOCIAL_UNAVAILABLE")
    low, high = pair(owner, target.id)
    await db.execute(
        update(ConnectionRequest)
        .where(
            ConnectionRequest.user_id_low == low,
            ConnectionRequest.user_id_high == high,
            ConnectionRequest.status == "pending",
            ConnectionRequest.expires_at <= utcnow(),
        )
        .values(status="expired", resolved_at=utcnow())
    )
    row = await pending(db, owner, target.id)
    if row:
        if row.sender_id != owner:
            raise AuthError(409, "INCOMING_REQUEST_EXISTS")
        return await request_view(db, owner, row)
    row = ConnectionRequest(
        sender_id=owner,
        receiver_id=target.id,
        user_id_low=low,
        user_id_high=high,
        expires_at=utcnow() + timedelta(days=7),
    )
    db.add(row)
    await db.flush()
    notify(db, row, target.id, owner, "connection_request_received")
    await db.flush()
    return await request_view(db, owner, row)


async def transition(actor: Actor, target: User, request_id: UUID, action: str) -> RequestView:
    db, owner = actor.db, actor.user.id
    row = await db.scalar(
        select(ConnectionRequest)
        .where(ConnectionRequest.id == request_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None or (row.sender_id if action == "cancel" else row.receiver_id) != owner:
        raise AuthError(404, "SOCIAL_UNAVAILABLE")
    if (await access(db, owner, target.id)).blocked:
        raise AuthError(404, "SOCIAL_UNAVAILABLE")
    expected = {"accept": "accepted", "reject": "rejected", "cancel": "cancelled"}[action]
    if row.status == expected:
        return await request_view(db, owner, row)
    if row.status != "pending":
        raise AuthError(409, "REQUEST_FINALIZED")
    if row.expires_at <= utcnow():
        row.status, row.resolved_at = "expired", utcnow()
        return await request_view(db, owner, row)
    if action == "accept":
        # Receiving requests is revocable; acceptance explicitly consents even if
        # the sender's general discovery setting is off.
        privacy = await db.get(PrivacySettings, owner)
        if privacy is None or privacy.connection_requests != "discoverable":
            raise AuthError(404, "SOCIAL_UNAVAILABLE")
        low, high = pair(owner, target.id)
        if await db.get(Connection, (low, high)) is None:
            db.add(Connection(user_id_low=low, user_id_high=high))
            notify(db, row, row.sender_id, owner, "connection_request_accepted")
    row.status, row.resolved_at = expected, utcnow()
    await db.flush()
    return await request_view(db, owner, row)


async def remove_connection(actor: Actor, target: User) -> None:
    low, high = pair(actor.user.id, target.id)
    await actor.db.execute(
        delete(Connection).where(Connection.user_id_low == low, Connection.user_id_high == high)
    )


async def block(actor: Actor, target: User) -> None:
    db, owner = actor.db, actor.user.id
    # A previously blocked target can be re-blocked idempotently, but an arbitrary
    # hidden handle cannot be probed. Incoming explicit requests allow reporting/blocking.
    existing = await db.get(UserBlock, (owner, target.id))
    incoming = await pending(db, owner, target.id)
    if (
        existing is None
        and await visible_person(db, owner, target) is None
        and incoming is None
        and not (await access(db, owner, target.id)).connected
    ):
        raise AuthError(404, "SOCIAL_UNAVAILABLE")
    if existing is None:
        db.add(UserBlock(blocker_id=owner, blocked_id=target.id))
    await remove_connection(actor, target)
    low, high = pair(owner, target.id)
    await db.execute(
        update(ConnectionRequest)
        .where(
            ConnectionRequest.user_id_low == low,
            ConnectionRequest.user_id_high == high,
            ConnectionRequest.status == "pending",
        )
        .values(status="cancelled", resolved_at=utcnow())
    )
    await db.execute(
        delete(SocialNotification).where(
            or_(
                and_(
                    SocialNotification.recipient_id == owner,
                    SocialNotification.actor_id == target.id,
                ),
                and_(
                    SocialNotification.recipient_id == target.id,
                    SocialNotification.actor_id == owner,
                ),
            )
        )
    )


async def report(actor: Actor, target: User, body: ReportInput) -> ReportReceipt:
    db, owner = actor.db, actor.user.id
    own_block = await db.get(UserBlock, (owner, target.id))
    incoming = await pending(db, owner, target.id)
    if (
        own_block is None
        and incoming is None
        and await visible_person(db, owner, target) is None
        and not (await access(db, owner, target.id)).connected
    ):
        raise AuthError(404, "SOCIAL_UNAVAILABLE")
    row = await db.scalar(
        select(UserReport)
        .where(
            UserReport.reporter_id == owner,
            UserReport.target_id == target.id,
            UserReport.reason == body.reason,
            UserReport.created_at > utcnow() - timedelta(days=1),
        )
        .order_by(UserReport.created_at.desc())
        .limit(1)
    )
    if row is None:
        row = UserReport(
            reporter_id=owner,
            target_id=target.id,
            reason=body.reason,
            description=body.description.strip(),
            expires_at=utcnow() + timedelta(days=90),
        )
        db.add(row)
        await db.flush()
    return ReportReceipt(id=row.id, status=row.status)
