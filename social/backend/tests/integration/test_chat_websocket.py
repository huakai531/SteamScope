"""Actual localhost sockets, two API instances, isolated PostgreSQL and Redis."""

import asyncio
import json
import socket
import time
from contextlib import AsyncExitStack
from uuid import uuid4

import httpx
import pytest
import uvicorn
from sqlalchemy import update
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from steamscope_social.main import create_app
from steamscope_social.modules.auth.security import digest, session_cookie
from steamscope_social.modules.chat.realtime import pulse
from steamscope_social.modules.privacy.models import PrivacySettings
from tests.integration.test_chat import chat  # noqa: F401
from tests.integration.test_players import players  # noqa: F401
from tests.integration.test_social import social  # noqa: F401

pytestmark = pytest.mark.integration


class ReadyServer(uvicorn.Server):
    def __init__(self, config):
        super().__init__(config)
        self.ready = asyncio.Event()

    async def startup(self, sockets=None):
        await super().startup(sockets=sockets)
        self.ready.set()


async def event(ws, kind, predicate=lambda value: True):
    async with asyncio.timeout(8):
        while True:
            item = json.loads(await ws.recv())
            if item.get("type") == kind and predicate(item):
                return item


@pytest.fixture
async def sockets(chat):  # noqa: F811
    auth, clients, *_ = chat

    def no_steam(request):
        raise AssertionError("Chat must never contact Steam")

    second = create_app(auth.config, provider_transport=httpx.MockTransport(no_steam))
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(second.router.lifespan_context(second))
        assert second.state.resources is not auth.resources
        servers = []
        tasks = []
        ports = []
        listeners = []
        try:
            for app in [auth.app, second]:
                listener = socket.socket()
                listener.bind(("127.0.0.1", 0))
                listeners.append(listener)
                ports.append(listener.getsockname()[1])
                server = ReadyServer(
                    uvicorn.Config(
                        app,
                        lifespan="off",
                        access_log=False,
                        log_config=None,
                        log_level="critical",
                        ws="auto",
                        ws_max_size=1024,
                    )
                )
                servers.append(server)
                tasks.append(asyncio.create_task(server.serve(sockets=[listener])))
                async with asyncio.timeout(5):
                    await server.ready.wait()

            async def open_ws(name="A", instance=0, origin=None, query="", credential=True):
                headers = (
                    {
                        "Cookie": session_cookie(auth.config)
                        + "="
                        + clients[name].cookies[session_cookie(auth.config)]
                    }
                    if credential
                    else {}
                )
                return await stack.enter_async_context(
                    connect(
                        f"ws://127.0.0.1:{ports[instance]}/api/v1/ws" + query,
                        origin=origin or auth.config.browser_origin,
                        additional_headers=headers,
                        proxy=None,
                    )
                )

            yield chat, open_ws, ports
        finally:
            await stack.aclose()
            for server in servers:
                server.should_exit = True
            await asyncio.wait_for(asyncio.gather(*tasks), 8)
            for listener in listeners:
                listener.close()


async def watch(ws, cid):
    await event(ws, "ready")
    await ws.send(json.dumps(dict(type="watch", conversation_id=cid)))
    return await event(ws, "conversation.state")


async def test_stalled_pubsub_is_bounded_and_committed_history_recovers(sockets, monkeypatch):
    from redis.asyncio.client import PubSub

    harness, open_ws, _ = sockets
    _, clients, _, _, _, _, cid, send = harness
    response = await send(body="Committed before transient delivery failure")
    assert response.status_code == 200
    a = await open_ws("A")
    await watch(a, cid)

    async def stalled(*args, **kwargs):
        await asyncio.Event().wait()

    started = time.monotonic()
    with monkeypatch.context() as patch:
        patch.setattr(PubSub, "get_message", stalled)
        await asyncio.wait_for(a.wait_closed(), 8)
        assert a.close_code == 1013
    assert time.monotonic() - started < 8
    recovered = await open_ws("A")
    await watch(recovered, cid)
    history = (await clients["A"].get(f"/api/v1/conversations/{cid}/messages")).json()
    assert [row["id"] for row in history["items"]] == [response.json()["id"]]


async def test_cross_instance_delivery_multitab_presence_read_and_typing(sockets):
    harness, open_ws, _ = sockets
    _, _, _, _, call, _, cid, send = harness
    a = await open_ws("A", 0)
    b = await open_ws("B", 1)
    b2 = await open_ws("B", 0)
    assert (await watch(a, cid))["presence"] == "online"
    await watch(b, cid)
    await watch(b2, cid)
    await send()
    await event(b, "message.created")
    await event(b2, "message.created")
    await call("B", f"/conversations/{cid}/read", body={"sequence": 1})
    await event(b2, "conversation.read")
    await event(a, "conversation.state", lambda e: e["peer_read_sequence"] == 1)
    await b.send(json.dumps(dict(type="typing", conversation_id=cid, active=True)))
    await event(a, "conversation.state", lambda e: e["typing"])
    await b.close()
    state = await event(a, "conversation.state", lambda e: not e["typing"])
    assert state["presence"] == "online"  # second B tab is still connected
    await b2.send(json.dumps(dict(type="typing", conversation_id=cid, active=True)))
    await event(a, "conversation.state", lambda e: e["typing"])
    await event(a, "conversation.state", lambda e: not e["typing"])  # automatic expiry
    await b2.close()
    await event(a, "conversation.state", lambda e: e["presence"] == "offline")


async def test_presence_private_connection_removal_and_typing_denial(sockets):
    harness, open_ws, _ = sockets
    auth, _, accounts, ids, call, _, cid, _ = harness
    a = await open_ws("A")
    b = await open_ws("B", 1)
    await watch(a, cid)
    await watch(b, cid)
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(
            update(PrivacySettings)
            .where(PrivacySettings.user_id == ids["B"])
            .values(presence="private")
        )
    await event(a, "conversation.state", lambda e: e["presence"] == "unavailable")
    await call("B", f"/connections/{accounts['A']['handle']}", "DELETE")
    state = await event(a, "conversation.state", lambda e: not e["can_send"])
    assert state["presence"] == "unavailable" and not state["typing"]
    await b.send(json.dumps(dict(type="typing", conversation_id=cid, active=True)))
    assert (await event(b, "error"))["code"] == "CHAT_UNAVAILABLE"


async def test_block_existing_sockets_hide_history_and_stop_events(sockets):
    harness, open_ws, _ = sockets
    _, clients, accounts, _, call, _, cid, send = harness
    a = await open_ws("A")
    b = await open_ws("B", 1)
    await watch(a, cid)
    await watch(b, cid)
    await b.send(json.dumps(dict(type="typing", conversation_id=cid, active=True)))
    await event(a, "conversation.state", lambda e: e["typing"])
    started = time.monotonic()
    await call("A", f"/blocks/{accounts['B']['handle']}")
    await event(a, "conversation.unavailable")
    await event(b, "conversation.unavailable")
    assert time.monotonic() - started < 8
    assert (await send()).status_code == 404
    assert (await clients["B"].get(f"/api/v1/conversations/{cid}/messages")).status_code == 404
    await b.send(json.dumps(dict(type="typing", conversation_id=cid, active=True)))
    await event(b, "error")


@pytest.mark.parametrize("mode", ["logout", "logout-all", "delete", "revoke", "disable"])
async def test_session_revocation_closes_active_socket_within_bound(sockets, mode):
    harness, open_ws, _ = sockets
    auth, clients, _, ids, call, _, cid, _ = harness
    a = await open_ws("A")
    await watch(a, cid)
    started = time.monotonic()
    if mode in {"logout", "logout-all"}:
        await call("A", "/auth/" + mode)
    elif mode == "delete":
        await call("A", "/me", "DELETE", {"confirmation": "DELETE"})
    elif mode == "revoke":
        sessions = (await clients["A"].get("/api/v1/me/sessions")).json()
        # Use the actual session API shape; no socket credential is put in a URL.
        rows = sessions if isinstance(sessions, list) else sessions["items"]
        await call("A", f"/me/sessions/{rows[0]['id']}", "DELETE")
    else:
        from steamscope_social.modules.users.models import User

        async with auth.resources.sessions() as db, db.begin():
            await db.execute(update(User).where(User.id == ids["A"]).values(status="disabled"))
    with pytest.raises(ConnectionClosed):
        async with asyncio.timeout(8):
            while True:
                await a.recv()
    assert time.monotonic() - started < 8


@pytest.mark.parametrize("mode", ["origin", "anonymous", "query"])
async def test_socket_handshake_rejects_untrusted_origin_credentials_in_url(sockets, mode):
    _, open_ws, _ = sockets
    with pytest.raises(InvalidStatus) as caught:
        await open_ws(
            origin="https://untrusted.invalid" if mode == "origin" else None,
            credential=mode != "anonymous",
            query="?token=synthetic" if mode == "query" else "",
        )
    assert caught.value.response.status_code == 403


async def test_unrelated_socket_cannot_subscribe_or_receive_hints(sockets):
    harness, open_ws, _ = sockets
    _, _, _, _, _, _, cid, send = harness
    c = await open_ws("C")
    await event(c, "ready")
    await c.send(json.dumps(dict(type="watch", conversation_id=cid)))
    denied = await event(c, "conversation.unavailable")
    assert set(denied) == {"v", "type", "conversation_id"}  # echoes only supplied opaque id
    await send()
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(1.3):
            await c.recv()
    await c.send(json.dumps(dict(type="unknown", claim_user_id=str(uuid4()))))
    assert (await event(c, "error"))["code"] == "INVALID_EVENT"


async def test_disconnect_gap_recovery_and_expiring_orphan_presence(sockets):
    harness, open_ws, _ = sockets
    auth, c, _, ids, _, _, cid, send = harness
    b = await open_ws("B")
    await watch(b, cid)
    first = (await send()).json()
    await event(b, "message.created")
    await b.close()
    second = (await send()).json()
    reconnect = await open_ws("B", 1)
    await watch(reconnect, cid)
    missed = (
        await c["B"].get(
            f"/api/v1/conversations/{cid}/messages", params={"after": first["sequence"]}
        )
    ).json()["items"]
    assert [m["id"] for m in missed] == [second["id"]]
    # Synthetic crashed socket expires without a clean disconnect.
    key = auth.config.redis_prefix + "chat:presence:" + digest(str(ids["C"]))
    await pulse(auth.resources, key, "orphan", "add", 1)
    assert await pulse(auth.resources, key) == 1
    await asyncio.sleep(1.1)
    assert await pulse(auth.resources, key) == 0


async def test_typing_block_race_and_frame_rate_limit(sockets):
    harness, open_ws, _ = sockets
    auth, _, a, ids, call, _, cid, _ = harness
    b = await open_ws("B")
    await watch(b, cid)
    await asyncio.gather(
        b.send(json.dumps(dict(type="typing", conversation_id=cid, active=True))),
        call("A", f"/blocks/{a['B']['handle']}"),
    )
    await event(b, "conversation.unavailable")
    await auth.resources.redis.set(
        auth.config.redis_prefix + "rate:chat-events:" + digest(str(ids["B"])), 180, ex=60
    )
    await b.send(json.dumps(dict(type="ping")))
    await asyncio.wait_for(b.wait_closed(), 8)
    assert b.close_code == 4403  # A flood is disconnected, not an endless error stream.
