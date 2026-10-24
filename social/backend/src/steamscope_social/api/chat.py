from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import select

from steamscope_social.modules.auth.security import (
    AuthError,
    authenticated,
    config_for,
    get_cookie,
    rate_limit,
    resources_for,
    session_cookie,
)
from steamscope_social.modules.chat import service
from steamscope_social.modules.chat.models import Conversation
from steamscope_social.modules.chat.schemas import (
    ConversationList,
    ConversationView,
    DirectInput,
    MessagePage,
    MessageReportInput,
    MessageView,
    ReadInput,
    SendInput,
)
from steamscope_social.modules.social.schemas import ReportReceipt

router = APIRouter(prefix="/api/v1", tags=["Direct chat"])
Cursor = Annotated[int | None, Query(ge=0, le=9007199254740991)]


def token_for(request: Request) -> str:
    return get_cookie(request, session_cookie(config_for(request)))


async def authorize_write(
    request: Request, group: str = "chat-send", limit: int = 60, seconds: int = 60
) -> None:
    async with authenticated(request, write=True) as actor:
        await rate_limit(request, group, str(actor.user.id), limit, seconds)


@router.post("/conversations/direct", response_model=ConversationView)
async def direct(request: Request, body: DirectInput) -> ConversationView:
    await authorize_write(request, "chat-create", 10)
    async with service.transaction(
        resources_for(request), config_for(request), token_for(request), handle=body.handle
    ) as (actor, target, _):
        row = await service.direct(actor, target)
        result = await service.view(actor, target, row)
    await service.publish(
        resources_for(request), config_for(request), result.id, "conversation.changed"
    )
    return result


@router.get("/conversations", response_model=ConversationList)
async def conversations(
    request: Request, cursor: UUID | None = None, limit: int = Query(default=25, ge=1, le=50)
) -> ConversationList:
    async with authenticated(request) as actor:
        await rate_limit(request, "chat-read", str(actor.user.id), 240, 60)
        # Immutable UUID ordering prevents movement between pages after a send.
        query = select(Conversation.id).where(
            (Conversation.user_id_low == actor.user.id)
            | (Conversation.user_id_high == actor.user.id)
        )
        if cursor:
            query = query.where(Conversation.id < cursor)
        ids = list(await actor.db.scalars(query.order_by(Conversation.id.desc()).limit(limit + 1)))
    items = []
    for cid in ids[:limit]:
        try:
            async with service.transaction(
                resources_for(request), config_for(request), token_for(request), conversation_id=cid
            ) as (actor, target, row):
                assert row is not None
                items.append(await service.view(actor, target, row))
        except AuthError as exc:
            if exc.status != 404:
                raise
    return ConversationList(items=items, next_cursor=ids[limit - 1] if len(ids) > limit else None)


@router.get("/conversations/{conversation_id}", response_model=ConversationView)
async def conversation(request: Request, conversation_id: UUID) -> ConversationView:
    async with service.transaction(
        resources_for(request),
        config_for(request),
        token_for(request),
        conversation_id=conversation_id,
    ) as (actor, target, row):
        assert row is not None
        await rate_limit(request, "chat-read", str(actor.user.id), 240, 60)
        return await service.view(actor, target, row)


@router.get("/conversations/{conversation_id}/messages", response_model=MessagePage)
async def messages(
    request: Request,
    conversation_id: UUID,
    before: Cursor = None,
    after: Cursor = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> MessagePage:
    async with service.transaction(
        resources_for(request),
        config_for(request),
        token_for(request),
        conversation_id=conversation_id,
    ) as (actor, _, row):
        assert row is not None
        await rate_limit(request, "chat-read", str(actor.user.id), 240, 60)
        return await service.history(actor, row, before, after, limit)


@router.post("/conversations/{conversation_id}/messages", response_model=MessageView)
async def send_message(request: Request, conversation_id: UUID, body: SendInput) -> MessageView:
    await authorize_write(request)
    async with service.transaction(
        resources_for(request),
        config_for(request),
        token_for(request),
        conversation_id=conversation_id,
    ) as (actor, target, row):
        assert row is not None
        result = await service.send(actor, target, row, body)
    # Exiting transaction has successfully committed before either delivery or HTTP success.
    service.logger.info("message_persisted:%s", result.id)
    await service.publish(
        resources_for(request), config_for(request), conversation_id, "message.created"
    )
    return result


@router.post("/conversations/{conversation_id}/read", status_code=204)
async def read(request: Request, conversation_id: UUID, body: ReadInput) -> Response:
    await authorize_write(request, "chat-read-ack", 60)
    async with service.transaction(
        resources_for(request),
        config_for(request),
        token_for(request),
        conversation_id=conversation_id,
    ) as (actor, _, row):
        assert row is not None
        await service.read(actor, row, body.sequence)
    await service.publish(
        resources_for(request), config_for(request), conversation_id, "conversation.read"
    )
    return Response(status_code=204)


@router.delete("/messages/{message_id}", status_code=204)
async def delete(request: Request, message_id: UUID) -> Response:
    await authorize_write(request, "chat-delete", 30)
    async with service.transaction(
        resources_for(request), config_for(request), token_for(request), message_id=message_id
    ) as (actor, _, row):
        assert row is not None
        cid = row.id
        await service.delete_message(actor, message_id)
    await service.publish(resources_for(request), config_for(request), cid, "message.deleted")
    return Response(status_code=204)


@router.post("/messages/{message_id}/report", response_model=ReportReceipt)
async def report(request: Request, message_id: UUID, body: MessageReportInput) -> ReportReceipt:
    await authorize_write(request, "chat-report", 3, 3600)
    async with service.transaction(
        resources_for(request), config_for(request), token_for(request), message_id=message_id
    ) as (actor, target, row):
        assert row is not None
        return await service.report_message(actor, target, row, message_id, body)
