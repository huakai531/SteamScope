"""All durable writes share the Phase 5 ordered user locks, then commit before publish."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID

from redis.exceptions import RedisError
from sqlalchemy import func, select

from steamscope_social.core.config import Settings
from steamscope_social.core.database import utcnow
from steamscope_social.core.resources import Resources
from steamscope_social.modules.auth.models import UserSession
from steamscope_social.modules.auth.security import Actor, AuthError, digest, resolve_actor
from steamscope_social.modules.chat.models import (
    Conversation,
    ConversationMember,
    Message,
    MessageReport,
)
from steamscope_social.modules.chat.schemas import (
    ConversationView,
    MessagePage,
    MessageReportInput,
    MessageView,
    SendInput,
)
from steamscope_social.modules.privacy.models import PrivacySettings
from steamscope_social.modules.social.policy import access, pair
from steamscope_social.modules.social.schemas import Person, ReportReceipt
from steamscope_social.modules.social.service import verified_user
from steamscope_social.modules.users.models import User

logger = logging.getLogger("steamscope_social.chat")


@asynccontextmanager
async def transaction(
    resources: Resources,
    config: Settings,
    token: str,
    *,
    conversation_id: UUID | None = None,
    message_id: UUID | None = None,
    handle: str | None = None,
) -> AsyncIterator[tuple[Actor, User, Conversation | None]]:
    async with resources.sessions() as db, db.begin():
        session = (
            await db.scalar(select(UserSession).where(UserSession.token_digest == digest(token)))
            if token
            else None
        )
        if session is None:
            raise AuthError(401, "AUTH_REQUIRED")
        owner = session.user_id
        if message_id is not None:
            message = await db.get(Message, message_id)
            if message is None:
                raise AuthError(404, "CHAT_UNAVAILABLE")
            conversation_id = message.conversation_id
        conversation = await db.get(Conversation, conversation_id) if conversation_id else None
        if conversation_id:
            if conversation is None or owner not in {
                conversation.user_id_low,
                conversation.user_id_high,
            }:
                raise AuthError(404, "CHAT_UNAVAILABLE")
            target_id = (
                conversation.user_id_high
                if owner == conversation.user_id_low
                else conversation.user_id_low
            )
        else:
            assert handle is not None
            target_id = (await verified_user(db, handle)).id
        if target_id == owner:
            raise AuthError(404, "CHAT_UNAVAILABLE")
        users = list(
            await db.scalars(
                select(User)
                .where(User.id.in_(pair(owner, target_id)))
                .order_by(User.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        if len(users) != 2 or any(u.status != "active" for u in users):
            raise AuthError(404, "CHAT_UNAVAILABLE")
        actor = await resolve_actor(db, token, config)
        target = next(u for u in users if u.id == target_id)
        if (handle is not None and target.handle.lower() != handle.lower()) or (
            await access(db, owner, target_id)
        ).blocked:
            raise AuthError(404, "CHAT_UNAVAILABLE")
        if conversation_id:
            conversation = await db.scalar(
                select(Conversation)
                .where(Conversation.id == conversation_id)
                .execution_options(populate_existing=True)
            )
            if (
                conversation is None
                or await db.get(ConversationMember, (conversation_id, owner)) is None
            ):
                raise AuthError(404, "CHAT_UNAVAILABLE")
        yield actor, target, conversation


async def can_send(actor: Actor, target: User) -> bool:
    policy = await access(actor.db, actor.user.id, target.id)
    a = await actor.db.get(PrivacySettings, actor.user.id)
    b = await actor.db.get(PrivacySettings, target.id)
    return bool(
        policy.connected
        and not policy.blocked
        and a
        and b
        and a.messaging == b.messaging == "connections"
    )


async def require_send(actor: Actor, target: User) -> None:
    if not await can_send(actor, target):
        raise AuthError(404, "CHAT_UNAVAILABLE")


def message_view(row: Message, owner: UUID) -> MessageView:
    return MessageView(
        id=row.id,
        conversation_id=row.conversation_id,
        sequence=row.sequence,
        mine=row.sender_id == owner,
        client_message_id=row.client_message_id if row.sender_id == owner else None,
        body=None if row.deleted_at else row.body,
        created_at=row.created_at,
        deleted_at=row.deleted_at,
    )


async def view(actor: Actor, target: User, row: Conversation) -> ConversationView:
    db, owner = actor.db, actor.user.id
    mine = await db.get(ConversationMember, (row.id, owner))
    peer = await db.get(ConversationMember, (row.id, target.id))
    assert mine is not None and peer is not None
    last = await db.scalar(
        select(Message)
        .where(Message.conversation_id == row.id)
        .order_by(Message.sequence.desc())
        .limit(1)
    )
    unread = await db.scalar(
        select(func.count())
        .select_from(Message)
        .where(
            Message.conversation_id == row.id,
            Message.sequence > mine.last_read_sequence,
            Message.sender_id != owner,
            Message.deleted_at.is_(None),
        )
    )
    privacy = await db.get(PrivacySettings, target.id)
    policy = await access(db, owner, target.id)
    person = (
        Person(handle=target.handle, display_name=target.display_name)
        if privacy and policy.permits(privacy.profile)
        else None
    )
    return ConversationView(
        id=row.id,
        person=person,
        can_send=await can_send(actor, target),
        created_at=row.created_at,
        last_message_at=row.last_message_at,
        last_message=message_view(last, owner) if last else None,
        unread_count=unread or 0,
        last_read_sequence=mine.last_read_sequence,
        peer_read_sequence=peer.last_read_sequence,
        latest_sequence=row.next_sequence - 1,
    )


async def direct(actor: Actor, target: User) -> Conversation:
    await require_send(actor, target)
    low, high = pair(actor.user.id, target.id)
    row = await actor.db.scalar(
        select(Conversation).where(
            Conversation.user_id_low == low, Conversation.user_id_high == high
        )
    )
    if row is None:
        row = Conversation(user_id_low=low, user_id_high=high)
        actor.db.add(row)
        await actor.db.flush()
        actor.db.add_all(
            [ConversationMember(conversation_id=row.id, user_id=uid) for uid in (low, high)]
        )
        await actor.db.flush()
    return row


async def send(actor: Actor, target: User, row: Conversation, body: SendInput) -> MessageView:
    await require_send(actor, target)
    existing = await actor.db.scalar(
        select(Message).where(
            Message.sender_id == actor.user.id, Message.client_message_id == body.client_message_id
        )
    )
    if existing:
        if existing.conversation_id != row.id or (
            existing.deleted_at is None and existing.body != body.body
        ):
            raise AuthError(409, "MESSAGE_ID_CONFLICT")
        logger.info("message_duplicate_retry")
        return message_view(existing, actor.user.id)
    message = Message(
        conversation_id=row.id,
        sender_id=actor.user.id,
        client_message_id=body.client_message_id,
        sequence=row.next_sequence,
        body=body.body,
    )
    row.next_sequence += 1
    row.last_message_at = utcnow()
    actor.db.add(message)
    await actor.db.flush()
    return message_view(message, actor.user.id)


async def history(
    actor: Actor, row: Conversation, before: int | None, after: int | None, limit: int
) -> MessagePage:
    if before is not None and after is not None:
        raise AuthError(422, "INVALID_CURSOR")
    query = select(Message).where(Message.conversation_id == row.id)
    if before is not None:
        query = query.where(Message.sequence < before)
    if after is not None:
        query = query.where(Message.sequence > after)
    rows = list(
        await actor.db.scalars(
            query.order_by(
                Message.sequence.asc() if after is not None else Message.sequence.desc()
            ).limit(limit + 1)
        )
    )
    more = len(rows) > limit
    rows = rows[:limit]
    if after is None:
        rows.reverse()
    return MessagePage(
        items=[message_view(m, actor.user.id) for m in rows],
        next_before=rows[0].sequence if more and after is None else None,
        next_after=rows[-1].sequence if more and after is not None else None,
    )


async def read(actor: Actor, row: Conversation, sequence: int) -> None:
    if sequence >= row.next_sequence:
        raise AuthError(422, "INVALID_CURSOR")
    member = await actor.db.get(ConversationMember, (row.id, actor.user.id))
    assert member is not None
    member.last_read_sequence = max(member.last_read_sequence, sequence)


async def delete_message(actor: Actor, message_id: UUID) -> None:
    row = await actor.db.get(Message, message_id)
    if row is None or row.sender_id != actor.user.id:
        raise AuthError(404, "CHAT_UNAVAILABLE")
    row.deleted_at = row.deleted_at or utcnow()


async def report_message(
    actor: Actor,
    target: User,
    conversation: Conversation,
    message_id: UUID,
    body: MessageReportInput,
) -> ReportReceipt:
    message = await actor.db.get(Message, message_id)
    if message is None or message.sender_id == actor.user.id or message.deleted_at is not None:
        raise AuthError(404, "CHAT_UNAVAILABLE")
    row = await actor.db.scalar(
        select(MessageReport).where(
            MessageReport.reporter_id == actor.user.id,
            MessageReport.message_id == message_id,
            MessageReport.reason == body.reason,
        )
    )
    if row is None:
        row = MessageReport(
            reporter_id=actor.user.id,
            target_id=target.id,
            message_id=message_id,
            conversation_id=conversation.id,
            reason=body.reason,
            description=body.description.strip(),
            expires_at=utcnow() + timedelta(days=90),
        )
        actor.db.add(row)
        await actor.db.flush()
    return ReportReceipt(id=row.id, status=row.status)


async def publish(resources: Resources, config: Settings, conversation_id: UUID, kind: str) -> None:
    # Hints contain no bodies, credentials or identity. Consumers reauthorize
    # against PostgreSQL before disclosing even the conversation identifier.
    import json

    try:
        await resources.redis.publish(
            config.redis_prefix + "chat:events",
            json.dumps({"v": 1, "type": kind, "conversation_id": str(conversation_id)}),
        )
    except (RedisError, OSError, TimeoutError):
        logger.warning("chat_publish_failed_after_commit")
