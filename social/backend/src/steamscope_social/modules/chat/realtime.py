"""Authenticated delivery hints and ephemeral per-socket presence; no durable sends here."""

import asyncio
import json
import logging
import time
from typing import cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from steamscope_social.core.config import Settings
from steamscope_social.core.resources import Resources
from steamscope_social.modules.auth.security import (
    AuthError,
    digest,
    get_cookie,
    rate_limit,
    resolve_actor,
    session_cookie,
)
from steamscope_social.modules.chat import service
from steamscope_social.modules.chat.schemas import SocketInput
from steamscope_social.modules.privacy.models import PrivacySettings

router = APIRouter()
logger = logging.getLogger("steamscope_social.realtime")

# Expiring sorted sets aggregate independent tabs and instances without SCAN.
PULSE = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
if ARGV[3] == 'remove' then redis.call('ZREM', KEYS[1], ARGV[2])
elseif ARGV[3] == 'add' then
  if not redis.call('ZSCORE', KEYS[1], ARGV[2])
     and redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[5]) then return -1 end
  redis.call('ZADD', KEYS[1], ARGV[4], ARGV[2])
end
redis.call('EXPIRE', KEYS[1], 60)
return redis.call('ZCARD', KEYS[1])
"""


async def pulse(
    resources: Resources, key: str, member: str = "", operation: str = "read", ttl: int = 30
) -> int:
    now = time.time()
    return int(await resources.redis.eval(PULSE, 1, key, now, member, operation, now + ttl, 16))


class Socket:
    def __init__(
        self, websocket: WebSocket, resources: Resources, config: Settings, token: str
    ) -> None:
        self.ws, self.resources, self.config, self.token = websocket, resources, config, token
        self.connection = str(uuid4())
        self.owner: UUID | None = None
        self.watched: UUID | None = None
        self.last_ping = time.monotonic()
        self.last_state = ""
        self.typing_key: str | None = None

    def presence_key(self, owner: UUID) -> str:
        return self.config.redis_prefix + "chat:presence:" + digest(str(owner))

    def type_key(self, cid: UUID, owner: UUID) -> str:
        return self.config.redis_prefix + "chat:typing:" + str(cid) + ":" + digest(str(owner))

    async def emit(self, event: dict[str, object]) -> None:
        async with asyncio.timeout(1):
            await self.ws.send_json({"v": 1, **event})

    async def authenticate(self) -> None:
        async with self.resources.sessions() as db, db.begin():
            actor = await resolve_actor(db, self.token, self.config)
            self.owner = actor.user.id

    async def stop_typing(self) -> None:
        if self.typing_key:
            await pulse(self.resources, self.typing_key, self.connection, "remove", 4)
            self.typing_key = None

    async def state(self) -> None:
        if self.watched is None:
            return
        try:
            async with service.transaction(
                self.resources, self.config, self.token, conversation_id=self.watched
            ) as (actor, target, row):
                assert row is not None
                enabled = await service.can_send(actor, target)
                if not enabled:
                    await self.stop_typing()
                privacy = await actor.db.get(PrivacySettings, target.id)
                visible = (
                    enabled
                    and privacy is not None
                    and privacy.presence in {"public", "connections"}
                )
                presence = (
                    (
                        "online"
                        if await pulse(self.resources, self.presence_key(target.id))
                        else "offline"
                    )
                    if visible
                    else "unavailable"
                )
                typing = (
                    bool(await pulse(self.resources, self.type_key(row.id, target.id)))
                    if enabled
                    else False
                )
                summary = await service.view(actor, target, row)
                event = dict(
                    type="conversation.state",
                    conversation_id=str(row.id),
                    can_send=enabled,
                    presence=presence,
                    typing=typing,
                    unread_count=summary.unread_count,
                    last_read_sequence=summary.last_read_sequence,
                    peer_read_sequence=summary.peer_read_sequence,
                    latest_sequence=summary.latest_sequence,
                )
                encoded = json.dumps(event, sort_keys=True)
                if encoded != self.last_state:
                    # Pair/session locks remain held through bounded delivery, so
                    # block, removal and revocation cannot race a disclosure.
                    await self.emit(event)
                    self.last_state = encoded
        except AuthError as exc:
            if exc.status != 404:
                raise
            await self.stop_typing()
            await self.emit(
                dict(type="conversation.unavailable", conversation_id=str(self.watched))
            )
            self.watched, self.last_state = None, ""

    async def hint(self, raw: str) -> None:
        try:
            event = json.loads(raw)
            cid = UUID(event["conversation_id"])
            kind = event["type"]
            if kind not in {
                "message.created",
                "message.deleted",
                "conversation.read",
                "conversation.changed",
            }:
                return
        except (ValueError, KeyError, TypeError):
            return
        try:
            async with service.transaction(
                self.resources, self.config, self.token, conversation_id=cid
            ) as (_, _, row):
                if row:
                    await self.emit(dict(type=kind, conversation_id=str(cid)))
        except AuthError as exc:
            if exc.status != 404:
                raise

    async def incoming(self, raw: str) -> None:
        if len(raw.encode("utf-8")) > 1024:
            raise AuthError(413, "INVALID_EVENT")
        await self.authenticate()
        assert self.owner is not None
        await rate_limit(cast(Request, self.ws), "chat-events", str(self.owner), 180, 60)
        try:
            event = SocketInput.model_validate_json(raw)
        except ValidationError:
            await self.emit(dict(type="error", code="INVALID_EVENT"))
            return
        if event.type == "ping":
            self.last_ping = time.monotonic()
            return
        if event.type == "watch":
            await self.stop_typing()
            self.watched, self.last_state = event.conversation_id, ""
            await self.state()
            return
        if event.conversation_id is None or event.conversation_id != self.watched:
            await self.emit(dict(type="error", code="CHAT_UNAVAILABLE"))
            return
        async with service.transaction(
            self.resources, self.config, self.token, conversation_id=event.conversation_id
        ) as (actor, target, row):
            await service.require_send(actor, target)
            await rate_limit(cast(Request, self.ws), "chat-typing", str(actor.user.id), 60, 60)
            assert row is not None
            self.typing_key = self.type_key(row.id, actor.user.id)
            await pulse(
                self.resources,
                self.typing_key,
                self.connection,
                "add" if event.active else "remove",
                4,
            )

    async def run(self) -> None:
        await self.authenticate()
        assert self.owner is not None
        await rate_limit(cast(Request, self.ws), "chat-connect", str(self.owner), 30, 60)
        if await pulse(self.resources, self.presence_key(self.owner), self.connection, "add") < 0:
            raise AuthError(429, "RATE_LIMITED")
        async with self.resources.redis.pubsub() as sub:
            await sub.subscribe(self.config.redis_prefix + "chat:events")
            await self.ws.accept()
            logger.info("websocket_open")
            await self.emit(dict(type="ready"))
            receiver = asyncio.create_task(self.ws.receive_text())
            last_tick = 0.0
            try:
                while True:
                    # Independent wall-clock revalidation cannot be starved by incoming events.
                    if time.monotonic() - last_tick >= 1:
                        if time.monotonic() - self.last_ping > 25:
                            break
                        async with asyncio.timeout(4):
                            await self.authenticate()
                            await pulse(
                                self.resources,
                                self.presence_key(self.owner),
                                self.connection,
                                "add",
                            )
                            await self.state()
                        last_tick = time.monotonic()
                    # Redis retry/backoff must not delay session revalidation indefinitely.
                    async with asyncio.timeout(4):
                        event = await sub.get_message(ignore_subscribe_messages=True, timeout=0.1)
                    if event:
                        async with asyncio.timeout(4):
                            await self.hint(event["data"])
                    done, _ = await asyncio.wait({receiver}, timeout=0.1)
                    if done:
                        raw = receiver.result()
                        receiver = asyncio.create_task(self.ws.receive_text())
                        try:
                            async with asyncio.timeout(4):
                                await self.incoming(raw)
                        except AuthError as exc:
                            if exc.status in {401, 429, 503, 413}:
                                raise
                            await self.emit(dict(type="error", code=exc.code))
            finally:
                receiver.cancel()
                await asyncio.gather(receiver, return_exceptions=True)


@router.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    config = cast(Settings, websocket.app.state.config)
    resources = cast(Resources, websocket.app.state.resources)
    socket: Socket | None = None
    code = 1000
    try:
        if websocket.headers.get("origin") != config.browser_origin or websocket.scope.get(
            "query_string"
        ):
            raise AuthError(403, "ORIGIN_REJECTED")
        token = get_cookie(cast(Request, websocket), session_cookie(config))
        socket = Socket(websocket, resources, config, token)
        await socket.run()
    except AuthError as exc:
        logger.info("websocket_authorization_denied")
        code = 1013 if exc.status == 503 else (4401 if exc.status == 401 else 4403)
    except WebSocketDisconnect:
        pass
    except (RedisError, SQLAlchemyError, OSError, TimeoutError):
        logger.warning("websocket_dependency_unavailable")
        code = 1013
    except Exception:
        logger.warning("websocket_invalid_or_interrupted")
        code = 1008
    finally:
        if socket and socket.owner:
            try:
                async with asyncio.timeout(2):
                    await socket.stop_typing()
                    await pulse(
                        resources, socket.presence_key(socket.owner), socket.connection, "remove"
                    )
            except (RedisError, OSError, TimeoutError):
                pass  # Redis expiry bounds stale presence after an outage/process crash.
        try:
            await websocket.close(code=code)
        except (RuntimeError, OSError, WebSocketDisconnect):
            pass
        logger.info("websocket_closed")
