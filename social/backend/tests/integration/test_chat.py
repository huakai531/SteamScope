"""Real isolated PostgreSQL/Redis messaging; provider traffic remains mocked."""

import asyncio
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from steamscope_social.core.database import utcnow
from steamscope_social.modules.administration.cleanup import purge_expired
from steamscope_social.modules.auth.models import UserSession
from steamscope_social.modules.chat import service
from steamscope_social.modules.chat.models import (
    Conversation,
    ConversationMember,
    Message,
    MessageReport,
)
from steamscope_social.modules.privacy.models import PrivacySettings
from steamscope_social.modules.social.models import Connection
from steamscope_social.modules.social.policy import pair
from steamscope_social.modules.users.models import User
from tests.integration.test_players import players  # noqa: F401
from tests.integration.test_social import social  # noqa: F401

pytestmark = pytest.mark.integration


@pytest.fixture
async def chat(social):  # noqa: F811
    auth, clients, accounts, ids, call, send_request = social
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(
            update(PrivacySettings)
            .where(PrivacySettings.user_id.in_(ids.values()))
            .values(messaging="connections", presence="connections")
        )
        low, high = pair(ids["A"], ids["B"])
        db.add(Connection(user_id_low=low, user_id_high=high))

    async def direct(a="A", b="B"):
        return await call(a, "/conversations/direct", body={"handle": accounts[b]["handle"]})

    response = await direct()
    assert response.status_code == 200, response.text
    cid = response.json()["id"]

    async def send(a="A", body="Synthetic text <b>{a,b}</b>", mid=None):
        return await call(
            a,
            f"/conversations/{cid}/messages",
            body={"client_message_id": str(mid or uuid4()), "body": body},
        )

    try:
        yield auth, clients, accounts, ids, call, direct, cid, send
    finally:
        async with auth.resources.sessions() as db, db.begin():
            await db.execute(
                delete(MessageReport).where(
                    or_(
                        MessageReport.reporter_id.in_(ids.values()),
                        MessageReport.target_id.in_(ids.values()),
                    )
                )
            )


async def test_direct_race_history_idempotency_and_read(chat):
    auth, c, a, ids, call, direct, cid, send = chat
    starts = await asyncio.gather(direct(), direct("B", "A"))
    assert all(r.status_code == 200 and r.json()["id"] == cid for r in starts)
    key = uuid4()
    retries = await asyncio.gather(send(mid=key), send(mid=key))
    assert all(r.status_code == 200 for r in retries)
    assert retries[0].json() == retries[1].json()
    assert (await send(mid=key, body="Changed request")).status_code == 409
    # Same key from the other sender is a separate logical message.
    assert (await send("B", mid=key)).status_code == 200
    assert (await c["B"].get(f"/api/v1/conversations/{cid}")).json()["unread_count"] == 1
    await call("B", f"/conversations/{cid}/read", body={"sequence": 2})
    await call("B", f"/conversations/{cid}/read", body={"sequence": 1})
    summary = (await c["B"].get(f"/api/v1/conversations/{cid}")).json()
    assert summary["last_read_sequence"] == 2 and summary["unread_count"] == 0
    assert (
        await call("B", f"/conversations/{cid}/read", body={"sequence": 100})
    ).status_code == 422
    async with auth.resources.sessions() as db:
        assert (
            await db.scalar(
                select(func.count()).select_from(Conversation).where(Conversation.id == UUID(cid))
            )
            == 1
        )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.conversation_id == UUID(cid))
            )
            == 2
        )


async def test_stable_before_after_pagination_concurrent_insert(chat):
    _, c, _, _, _, _, cid, send = chat
    await asyncio.gather(*(send(body=f"Row {i}") for i in range(8)))
    endpoint = f"/api/v1/conversations/{cid}/messages"
    page = (await c["B"].get(endpoint, params={"limit": 3})).json()
    assert [m["sequence"] for m in page["items"]] == [6, 7, 8]
    await send(body="New insert")
    older = (await c["B"].get(endpoint, params={"before": page["next_before"], "limit": 3})).json()
    assert [m["sequence"] for m in older["items"]] == [3, 4, 5]
    gap = (await c["B"].get(endpoint, params={"after": 5, "limit": 2})).json()
    assert [m["sequence"] for m in gap["items"]] == [6, 7] and gap["next_after"] == 7
    tail = (await c["B"].get(endpoint, params={"after": gap["next_after"]})).json()
    assert [m["sequence"] for m in tail["items"]] == [8, 9]
    assert (await c["B"].get(endpoint, params={"before": 3, "after": 2})).status_code == 422
    assert (await c["B"].get(endpoint, params={"limit": 101})).status_code == 422


@pytest.mark.parametrize(
    "body",
    ["", " \n\t", "x" * 2001, "x\n" * 51, "bad\x00text"],
    ids=["empty", "whitespace", "length", "newlines", "control"],
)
async def test_plain_text_bounds(chat, body):
    *_, send = chat
    assert (await send(body=body)).status_code == 422


async def test_unicode_and_html_remain_plain_text(chat):
    _, c, _, _, _, _, cid, send = chat
    row = (await send(body="e\u0301 🎮\r\n<script>alert(1)</script> {a,b}")).json()
    assert row["body"] == "é 🎮\n<script>alert(1)</script> {a,b}"
    history = (await c["B"].get(f"/api/v1/conversations/{cid}/messages")).json()["items"]
    assert history[0]["body"] == row["body"] and history[0]["client_message_id"] is None


async def test_publish_is_after_commit_and_failure_preserves_message(chat, monkeypatch):
    auth, c, _, _, _, _, cid, send = chat
    calls = []

    async def failed_publish(channel, payload):
        async with auth.resources.sessions() as db:
            count = await db.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.conversation_id == UUID(cid))
            )
            assert count == 1  # independent connection can observe the committed row
        calls.append(payload)
        raise RedisConnectionError("synthetic publish interruption")

    monkeypatch.setattr(auth.resources.redis, "publish", failed_publish)
    key = uuid4()
    response = await send(mid=key)
    assert response.status_code == 200 and len(calls) == 1
    assert (await c["B"].get(f"/api/v1/conversations/{cid}/messages")).json()["items"][0][
        "id"
    ] == response.json()["id"]
    # Lost acknowledgement/reconnect retry returns the same persisted record.
    assert (await send(mid=key)).json() == response.json()


async def test_persistence_failure_has_no_delivery(chat, monkeypatch):
    auth, c, _, _, _, _, cid, send = chat
    published = []
    original = service.send

    async def fail(*args, **kwargs):
        await original(*args, **kwargs)
        raise SQLAlchemyError("synthetic before commit failure")

    async def publish(*args):
        published.append(args)

    monkeypatch.setattr(service, "send", fail)
    monkeypatch.setattr(auth.resources.redis, "publish", publish)
    assert (await send()).status_code == 503
    assert not published
    assert (await c["B"].get(f"/api/v1/conversations/{cid}/messages")).json()["items"] == []


async def test_redis_unavailable_fails_before_write(chat, monkeypatch):
    auth, c, _, _, _, _, cid, send = chat

    async def failed(*args, **kwargs):
        raise RedisConnectionError("synthetic unavailable")

    monkeypatch.setattr(auth.resources.redis, "eval", failed)
    assert (await send()).status_code == 503
    async with auth.resources.sessions() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.conversation_id == UUID(cid))
            )
            == 0
        )


@pytest.mark.parametrize("viewer", ["C", "anonymous", "revoked", "blocked"])
async def test_authorization_matrix_no_conversation_disclosure(chat, viewer):
    auth, c, a, ids, call, _, cid, send = chat
    message = (await send()).json()
    key = "B" if viewer in {"revoked", "blocked"} else "C"
    client = await auth.client() if viewer == "anonymous" else c[key]
    headers = await auth.headers(c[key])
    if viewer == "revoked":
        async with auth.resources.sessions() as db, db.begin():
            await db.execute(
                update(UserSession)
                .where(UserSession.user_id == ids["B"])
                .values(revoked_at=utcnow())
            )
    if viewer == "blocked":
        await call("A", f"/blocks/{a['B']['handle']}")
    expected = 401 if viewer in {"anonymous", "revoked"} else 404
    for path, method, body in [
        (f"/conversations/{cid}", "GET", None),
        (f"/conversations/{cid}/messages", "GET", None),
        (
            f"/conversations/{cid}/messages",
            "POST",
            {"client_message_id": str(uuid4()), "body": "Denied"},
        ),
        (f"/conversations/{cid}/read", "POST", {"sequence": 1}),
        (f"/messages/{message['id']}", "DELETE", None),
        (f"/messages/{message['id']}/report", "POST", {"reason": "spam"}),
    ]:
        response = await client.request(method, "/api/v1" + path, headers=headers, json=body)
        assert response.status_code == expected, (viewer, path, response.text)
        assert message["body"] not in response.text and cid not in response.text


async def test_removed_connection_history_preserved_reconnection_reuses(chat):
    auth, c, a, ids, call, direct, cid, send = chat
    await send()
    assert (await call("A", f"/connections/{a['B']['handle']}", "DELETE")).status_code == 204
    assert (await send()).status_code == 404
    assert len((await c["B"].get(f"/api/v1/conversations/{cid}/messages")).json()["items"]) == 1
    assert not (await c["A"].get(f"/api/v1/conversations/{cid}")).json()["can_send"]
    async with auth.resources.sessions() as db, db.begin():
        low, high = pair(ids["A"], ids["B"])
        db.add(Connection(user_id_low=low, user_id_high=high))
    assert (await direct()).json()["id"] == cid
    assert (await send()).status_code == 200


async def test_messaging_privacy_and_imported_friend_do_not_grant(chat):
    auth, _, _, ids, _, direct, _, send = chat
    assert (await direct("A", "C")).status_code == 404
    assert (await direct("A", "A")).status_code == 404
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(
            update(PrivacySettings)
            .where(PrivacySettings.user_id == ids["B"])
            .values(messaging="nobody")
        )
    assert (await direct()).status_code == 404 and (await send()).status_code == 404


@pytest.mark.parametrize("change", ["block", "remove", "logout", "delete"])
async def test_send_security_change_races(chat, change):
    auth, c, a, ids, call, _, cid, send = chat

    async def mutate():
        if change == "block":
            return await call("B", f"/blocks/{a['A']['handle']}")
        if change == "remove":
            return await call("B", f"/connections/{a['A']['handle']}", "DELETE")
        if change == "logout":
            return await call("A", "/auth/logout-all")
        return await call("A", "/me", "DELETE", {"confirmation": "DELETE"})

    results = await asyncio.gather(send(), mutate())
    assert results[0].status_code in {200, 401, 404}
    assert results[1].status_code == 204, results[1].text
    assert (await send()).status_code in {401, 404}


async def test_read_send_and_delete_history_races(chat):
    _, c, _, _, call, _, cid, send = chat
    first = (await send()).json()
    responses = await asyncio.gather(
        send(), call("B", f"/conversations/{cid}/read", body={"sequence": 1})
    )
    assert [r.status_code for r in responses] == [200, 204]
    assert (await c["B"].get(f"/api/v1/conversations/{cid}")).json()["unread_count"] == 1
    responses = await asyncio.gather(
        call("A", f"/messages/{first['id']}", "DELETE"),
        c["B"].get(f"/api/v1/conversations/{cid}/messages"),
    )
    assert [r.status_code for r in responses] == [204, 200]
    final = (await c["B"].get(f"/api/v1/conversations/{cid}/messages")).json()["items"]
    assert final[0]["body"] is None and final[0]["deleted_at"]


async def test_report_tombstone_retention_deletion_and_clear_separation(chat):
    auth, c, a, ids, call, _, cid, send = chat
    message = (await send()).json()
    mid = message["id"]
    assert (await call("B", f"/messages/{mid}", "DELETE")).status_code == 404
    assert (await call("A", f"/messages/{mid}/report", body={"reason": "spam"})).status_code == 404
    report = (
        await call(
            "B",
            f"/messages/{mid}/report",
            body={"reason": "spam", "description": "Synthetic evidence"},
        )
    ).json()
    assert (await call("B", f"/messages/{mid}/report", body={"reason": "spam"})).json() == report
    assert (await call("A", f"/messages/{mid}", "DELETE")).status_code == 204
    assert (
        await call("A", "/me/steam/data", "DELETE", {"confirmation": "CLEAR STEAM DATA"})
    ).status_code == 204
    assert len((await c["B"].get(f"/api/v1/conversations/{cid}/messages")).json()["items"]) == 1
    async with auth.resources.sessions() as db, db.begin():
        row = await db.get(Message, UUID(mid))
        assert row.body == message["body"]
        row.deleted_at = utcnow() - timedelta(days=91)
        await db.flush()
        await purge_expired(db, auth.config)
        await db.refresh(row)
        assert row.body == ""
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(delete(User).where(User.id == ids["A"]))
        row = await db.get(MessageReport, UUID(report["id"]))
        assert (
            row.target_id is None
            and row.message_id is None
            and row.conversation_id is None
            and row.description == ""
        )
        assert await db.get(Conversation, UUID(cid)) is None


async def test_database_member_pair_and_message_id_constraints(chat):
    auth, _, _, ids, _, _, cid, send = chat
    with pytest.raises(DBAPIError):
        async with auth.resources.sessions() as db, db.begin():
            db.add(ConversationMember(conversation_id=UUID(cid), user_id=ids["C"]))
            await db.flush()
    original = (await send()).json()
    with pytest.raises(DBAPIError):
        async with auth.resources.sessions() as db, db.begin():
            db.add(
                Message(
                    conversation_id=UUID(cid),
                    sender_id=ids["A"],
                    client_message_id=UUID(original["client_message_id"]),
                    sequence=2,
                    body="duplicate",
                )
            )
            await db.flush()


async def test_chat_origin_csrf_limits_and_report_bounds(chat):
    auth, c, _, ids, call, _, cid, send = chat
    path = f"/api/v1/conversations/{cid}/messages"
    payload = {"client_message_id": str(uuid4()), "body": "Denied"}
    assert (await c["A"].post(path, json=payload)).status_code == 403
    headers = await auth.headers(c["A"])
    headers["Origin"] = "https://untrusted.invalid"
    assert (await c["A"].post(path, json=payload, headers=headers)).status_code == 403
    from steamscope_social.modules.auth.security import digest

    await auth.resources.redis.set(
        auth.config.redis_prefix + "rate:chat-send:" + digest(str(ids["A"])), 60, ex=60
    )
    assert (await send()).status_code == 429
    row = (await send("B")).json()
    for body in [{"reason": "bad"}, {"reason": "spam", "description": "x" * 1001}]:
        assert (await call("A", f"/messages/{row['id']}/report", body=body)).status_code == 422
