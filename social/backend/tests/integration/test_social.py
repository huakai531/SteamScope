"""Real isolated PostgreSQL/Redis social graph, privacy and competing transactions."""

import asyncio
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError

from steamscope_social.core.database import utcnow
from steamscope_social.modules.administration.cleanup import purge_expired
from steamscope_social.modules.privacy.models import PrivacySettings
from steamscope_social.modules.social.models import (
    Connection,
    ConnectionRequest,
    SocialNotification,
    UserBlock,
    UserReport,
)
from steamscope_social.modules.social.policy import pair
from steamscope_social.modules.steam.models import SteamFriend, SyncJob, SyncState, UserGame
from steamscope_social.modules.users.models import User
from tests.integration.test_players import APP, players  # noqa: F401

pytestmark = pytest.mark.integration


@pytest.fixture
async def social(players):  # noqa: F811 - pytest resolves the imported fixture by name
    auth, clients, accounts, ids = players
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(
            update(PrivacySettings)
            .where(PrivacySettings.user_id.in_(ids.values()))
            .values(discovery=True, connection_requests="discoverable")
        )
    headers = {n: await auth.headers(c) for n, c in clients.items()}

    async def call(actor, path, method="POST", body=None):
        return await clients[actor].request(
            method, "/api/v1" + path, headers=headers[actor], json=body
        )

    async def send(a="A", b="B"):
        response = await call(a, "/connection-requests", body={"handle": accounts[b]["handle"]})
        assert response.status_code == 200, response.text
        return response.json()["id"]

    try:
        yield auth, clients, accounts, ids, call, send
    finally:
        async with auth.resources.sessions() as db, db.begin():
            await db.execute(
                delete(UserReport).where(
                    or_(
                        UserReport.reporter_id.in_(ids.values()),
                        UserReport.target_id.in_(ids.values()),
                    )
                )
            )


async def counts(auth, ids):
    async with auth.resources.sessions() as db:
        return {
            "pending": await db.scalar(
                select(func.count())
                .select_from(ConnectionRequest)
                .where(
                    ConnectionRequest.sender_id.in_(ids.values()),
                    ConnectionRequest.status == "pending",
                )
            ),
            "connections": await db.scalar(
                select(func.count())
                .select_from(Connection)
                .where(Connection.user_id_low.in_(ids.values()))
            ),
            "notifications": await db.scalar(
                select(func.count())
                .select_from(SocialNotification)
                .where(SocialNotification.recipient_id.in_(ids.values()))
            ),
        }


async def test_request_lifecycle_permissions_and_notification_dedup(social):
    auth, c, a, ids, call, send = social
    request_id = await send()
    assert await send() == request_id
    assert (
        await call("B", "/connection-requests", body={"handle": a["A"]["handle"]})
    ).status_code == 409
    assert (await call("A", f"/connection-requests/{request_id}/accept")).status_code == 404
    assert (await call("C", f"/connection-requests/{request_id}/accept")).status_code == 404
    assert (await call("B", f"/connection-requests/{request_id}", "DELETE")).status_code == 404
    incoming = (await c["B"].get("/api/v1/connection-requests/incoming")).json()["items"]
    assert len(incoming) == 1 and incoming[0]["person"]["handle"] == a["A"]["handle"]
    assert (await call("B", f"/connection-requests/{request_id}/accept")).json()[
        "status"
    ] == "accepted"
    assert (await call("B", f"/connection-requests/{request_id}/accept")).status_code == 200
    assert await counts(auth, ids) == dict(pending=0, connections=1, notifications=2)
    assert (
        await call("A", "/connection-requests", body={"handle": a["B"]["handle"]})
    ).status_code == 404
    for actor, other in [("A", "B"), ("B", "A")]:
        assert (await c[actor].get("/api/v1/connections")).json()["items"][0]["handle"] == a[other][
            "handle"
        ]
    assert (await call("A", "/connections/" + a["B"]["handle"], "DELETE")).status_code == 204
    # Old acceptance retries report the finalized request but cannot reconnect.
    assert (await call("B", f"/connection-requests/{request_id}/accept")).status_code == 200
    assert (await counts(auth, ids))["connections"] == 0


@pytest.mark.parametrize(
    "action,actor,status", [("reject", "B", "rejected"), ("cancel", "A", "cancelled")]
)
async def test_terminal_request_never_reactivated(social, action, actor, status):
    auth, c, a, ids, call, send = social
    rid = await send()
    path = f"/connection-requests/{rid}" + ("/reject" if action == "reject" else "")
    method = "POST" if action == "reject" else "DELETE"
    assert (await call(actor, path, method)).json()["status"] == status
    assert (await call(actor, path, method)).status_code == 200
    assert (await call("B", f"/connection-requests/{rid}/accept")).status_code == 409
    assert (await counts(auth, ids)) == dict(pending=0, connections=0, notifications=1)


@pytest.mark.parametrize(
    "race",
    [
        "send_reverse",
        "send_duplicate",
        "accept_twice",
        "accept_reject",
        "accept_cancel",
        "accept_block",
        "remove_block",
    ],
)
async def test_transaction_races(social, race):
    auth, c, a, ids, call, send = social
    if race.startswith("send_"):
        other = "B" if race == "send_reverse" else "A"
        target = "A" if other == "B" else "B"
        results = await asyncio.gather(
            call("A", "/connection-requests", body={"handle": a["B"]["handle"]}),
            call(other, "/connection-requests", body={"handle": a[target]["handle"]}),
        )
        assert sorted(r.status_code for r in results) == (
            [200, 409] if race == "send_reverse" else [200, 200]
        )
        assert await counts(auth, ids) == dict(pending=1, connections=0, notifications=1)
        return
    rid = await send()
    if race == "remove_block":
        assert (await call("B", f"/connection-requests/{rid}/accept")).status_code == 200
        first = call("A", "/connections/" + a["B"]["handle"], "DELETE")
    else:
        first = call("B", f"/connection-requests/{rid}/accept")
    second = {
        "accept_twice": ("B", f"/connection-requests/{rid}/accept", "POST"),
        "accept_reject": ("B", f"/connection-requests/{rid}/reject", "POST"),
        "accept_cancel": ("A", f"/connection-requests/{rid}", "DELETE"),
        "accept_block": ("A", "/blocks/" + a["B"]["handle"], "POST"),
        "remove_block": ("A", "/blocks/" + a["B"]["handle"], "POST"),
    }[race]
    results = await asyncio.gather(first, call(*second))
    assert all(r.status_code in {200, 204, 404, 409} for r in results), [r.text for r in results]
    state = await counts(auth, ids)
    assert state["pending"] == 0 and state["connections"] <= 1 and state["notifications"] <= 2
    if race.endswith("block"):
        assert state["connections"] == state["notifications"] == 0
        async with auth.resources.sessions() as db:
            assert await db.get(UserBlock, (ids["A"], ids["B"]))
    elif race == "accept_twice":
        assert state == dict(pending=0, connections=1, notifications=2)


@pytest.mark.parametrize("blocker,blocked", [("A", "B"), ("B", "A")])
async def test_block_both_directions_privacy_and_unblock(social, blocker, blocked):
    auth, c, a, ids, call, send = social
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(
            update(PrivacySettings)
            .where(PrivacySettings.user_id == ids["B"])
            .values(library="connections", playtime="connections", achievements="connections")
        )
        db.add(
            SteamFriend(
                user_id=ids["A"], friend_steam_id64=a["B"]["steam_id"], observed_at=utcnow()
            )
        )
    path = "/api/v1/users/" + a["B"]["handle"]
    assert (await c["A"].get(path)).json()["game_count"] is None
    rid = await send()
    await call("B", f"/connection-requests/{rid}/accept")
    assert (await c["A"].get(path)).json()["game_count"] == 3
    assert (await call(blocker, "/blocks/" + a[blocked]["handle"])).status_code == 204
    assert (await call(blocker, "/blocks/" + a[blocked]["handle"])).status_code == 204
    for actor, other in [("A", "B"), ("B", "A")]:
        assert (await c[actor].get("/api/v1/users/" + a[other]["handle"])).status_code == 404
        for endpoint in ["/discovery/players", "/discovery/steam-friends"]:
            assert a[other]["handle"] not in (await c[actor].get("/api/v1" + endpoint)).text
        assert (
            await c[actor].get("/api/v1/users/search", params={"q": a[other]["handle"]})
        ).json()["items"] == []
        assert (
            await call(actor, "/connection-requests", body={"handle": a[other]["handle"]})
        ).status_code == 404
    assert (await call("B", f"/connection-requests/{rid}/accept")).status_code == 404
    async with auth.resources.sessions() as db:
        assert await db.get(SteamFriend, (ids["A"], a["B"]["steam_id"]))
    assert (await call(blocker, "/blocks/" + a[blocked]["handle"], "DELETE")).status_code == 204
    assert (await counts(auth, ids))["connections"] == 0
    assert (await c["A"].get(path)).json()["game_count"] is None
    assert (await c["B"].get("/api/v1/connection-requests/incoming")).json()["items"] == []


async def test_remove_and_block_cancel_pending_and_no_restore(social):
    auth, c, a, ids, call, send = social
    rid = await send()
    await call("B", "/blocks/" + a["A"]["handle"])
    await call("B", "/blocks/" + a["A"]["handle"], "DELETE")
    assert (await call("B", f"/connection-requests/{rid}/accept")).status_code == 409
    async with auth.resources.sessions() as db:
        assert (await db.get(ConnectionRequest, UUID(rid))).status == "cancelled"


async def test_search_limits_literal_queries_and_undiscoverability(social):
    auth, c, a, ids, call, send = social
    for endpoint in [
        "/users/search?q=abc",
        "/discovery/players",
        "/connections",
        "/blocks",
        "/notifications",
    ]:
        assert (await (await auth.client()).get("/api/v1" + endpoint)).status_code == 401
    for q in ["", "a", "  "]:
        assert (await c["A"].get("/api/v1/users/search", params={"q": q})).status_code == 422
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(
            update(User).where(User.id == ids["B"]).values(display_name="Literal {abc}%_<script>")
        )
    result = (await c["A"].get("/api/v1/users/search", params={"q": "{abc}%_"})).json()
    assert result["items"] == [
        dict(handle=a["B"]["handle"], display_name="Literal {abc}%_<script>", avatar_url=None)
    ]
    assert result["next_cursor"] is None
    for change in [
        dict(discovery=False),
        dict(discovery=True, profile="private"),
        dict(profile="connections"),
    ]:
        async with auth.resources.sessions() as db, db.begin():
            await db.execute(
                update(PrivacySettings).where(PrivacySettings.user_id == ids["B"]).values(**change)
            )
        assert (await c["A"].get("/api/v1/users/search", params={"q": a["B"]["handle"]})).json()[
            "items"
        ] == []
    assert (await c["A"].get("/api/v1/users/search", params={"q": a["B"]["steam_id"]})).json()[
        "items"
    ] == []
    # Unauthorized writes cannot be used as an exact hidden-handle lookup.
    for method, path in [("DELETE", "/connections/"), ("DELETE", "/blocks/"), ("POST", "/blocks/")]:
        assert (await call("A", path + a["B"]["handle"], method)).status_code == 404


async def test_ranking_only_authorized_fresh_evidence_and_steam_friend_hint(social):
    auth, c, a, ids, call, send = social
    before = (await c["A"].get("/api/v1/discovery/players")).json()
    b = next(r for r in before["items"] if r["person"]["handle"] == a["B"]["handle"])
    assert b["mutual_games"] == 2 and b["score"] == 25 and b["recent_overlap"] == 0
    assert a["C"]["handle"] not in str(before) and a["E"]["handle"] not in str(before)
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(
            update(UserGame)
            .where(UserGame.user_id == ids["C"])
            .values(total_minutes=999999, recent_minutes=9000)
        )
    assert (await c["A"].get("/api/v1/discovery/players")).json() == before
    async with auth.resources.sessions() as db, db.begin():
        db.add(
            SyncState(
                user_id=ids["A"],
                resource="friends",
                status="populated",
                code="OK",
                exposed=True,
                snapshot_id=UUID(int=123),
                last_success_at=utcnow(),
            )
        )
        db.add(
            SteamFriend(
                user_id=ids["A"], friend_steam_id64=a["B"]["steam_id"], observed_at=utcnow()
            )
        )
        db.add(
            SteamFriend(
                user_id=ids["A"], friend_steam_id64="76561198000000012", observed_at=utcnow()
            )
        )
    matched = (await c["A"].get("/api/v1/discovery/steam-friends")).json()["items"]
    assert len(matched) == 1 and matched[0]["steam_friend"] and matched[0]["score"] == 35
    assert a["B"]["steam_id"] not in str(matched) and "76561198000000012" not in str(matched)
    assert (await counts(auth, ids))["connections"] == 0
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(
            update(PrivacySettings)
            .where(PrivacySettings.user_id == ids["B"])
            .values(discovery=False)
        )
    assert (await c["A"].get("/api/v1/discovery/steam-friends")).json()["items"] == []


async def test_notification_isolation_read_states_and_current_privacy(social):
    auth, c, a, ids, call, send = social
    rid = await send()
    items = (await c["B"].get("/api/v1/notifications")).json()["items"]
    assert len(items) == 1 and items[0]["read_at"] is None
    nid = items[0]["id"]
    assert (await call("C", f"/notifications/{nid}/read")).status_code == 404
    assert (await call("B", f"/notifications/{nid}/read")).status_code == 204
    first = (await c["B"].get("/api/v1/notifications")).json()["items"][0]["read_at"]
    await call("B", f"/notifications/{nid}/read")
    assert (await c["B"].get("/api/v1/notifications")).json()["items"][0]["read_at"] == first
    await call("B", f"/connection-requests/{rid}/accept")
    await call("A", "/notifications/read-all")
    assert (await c["A"].get("/api/v1/notifications")).json()["items"][0]["read_at"]
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(
            update(PrivacySettings)
            .where(PrivacySettings.user_id == ids["B"])
            .values(profile="private")
        )
    assert (await c["A"].get("/api/v1/notifications")).json()["items"][0]["person"] is None


async def test_reports_validation_dedup_retention_block_and_no_reporter_disclosure(social):
    auth, c, a, ids, call, send = social
    for body in [
        dict(handle=a["B"]["handle"], reason="invalid"),
        dict(handle=a["B"]["handle"], reason="spam", description="x" * 1001),
        dict(handle=a["B"]["handle"], reason="spam", reporter_id=str(ids["C"])),
    ]:
        assert (await call("A", "/reports", body=body)).status_code == 422
    payload = dict(
        handle=a["B"]["handle"], reason="spam", description="<script>private {a,b}</script>"
    )
    one = await call("A", "/reports", body=payload)
    assert one.status_code == 200
    assert (await call("A", "/reports", body=payload)).json()["id"] == one.json()["id"]
    await call("A", "/blocks/" + a["B"]["handle"])
    assert (await call("A", "/reports", body=payload)).json()["id"] == one.json()["id"]
    assert (await call("A", "/reports", body=payload)).status_code == 429
    assert (await c["B"].get("/api/v1/notifications")).json()["items"] == []
    async with auth.resources.sessions() as db:
        assert (await db.get(UserReport, UUID(one.json()["id"]))).description == payload[
            "description"
        ]
    assert (
        await call("B", "/reports", body=dict(handle=a["B"]["handle"], reason="spam"))
    ).status_code == 422


async def test_delete_erases_graph_and_redacts_reports_clear_preserves_connections(social):
    auth, c, a, ids, call, send = social
    rid = await send()
    await call("B", f"/connection-requests/{rid}/accept")
    report_id = (
        await call(
            "B",
            "/reports",
            body=dict(
                handle=a["A"]["handle"], reason="spam", description="Delete personal evidence"
            ),
        )
    ).json()["id"]
    clear = await call("A", "/me/steam/data", "DELETE", {"confirmation": "CLEAR STEAM DATA"})
    assert clear.status_code == 204, clear.text
    assert (await counts(auth, ids))["connections"] == 1
    deletion = await call("A", "/me", "DELETE", {"confirmation": "DELETE"})
    assert deletion.status_code == 204, deletion.text
    assert await counts(auth, ids) == dict(pending=0, connections=0, notifications=0)
    async with auth.resources.sessions() as db, db.begin():
        row = await db.get(UserReport, UUID(report_id))
        assert row.target_id is None and row.description == "" and row.reason == "spam"
        row.expires_at = utcnow() - timedelta(seconds=1)
    async with auth.resources.sessions() as db, db.begin():
        await purge_expired(db, auth.config)
    async with auth.resources.sessions() as db:
        assert await db.get(UserReport, UUID(report_id)) is None


async def test_expiry_idor_csrf_rate_limit_and_redis_fail_closed(social, monkeypatch):
    from redis.exceptions import ConnectionError

    auth, c, a, ids, call, send = social
    assert (
        await c["A"].post("/api/v1/connection-requests", json={"handle": a["B"]["handle"]})
    ).status_code == 403
    rid = await send()
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(
            update(ConnectionRequest)
            .where(ConnectionRequest.id == UUID(rid))
            .values(expires_at=utcnow() - timedelta(seconds=1))
        )
    assert (await call("B", f"/connection-requests/{rid}/accept")).json()["status"] == "expired"
    assert (await c["A"].get("/api/v1/connection-requests/outgoing")).json()["items"] == []
    assert await send() != rid
    for _ in range(30):
        assert (await c["C"].get("/api/v1/users/search?q=unknown")).status_code == 200
    assert (await c["C"].get("/api/v1/users/search?q=unknown")).status_code == 429

    async def unavailable(*args, **kwargs):
        raise ConnectionError("fixture unavailable")

    monkeypatch.setattr(auth.resources.redis, "eval", unavailable)
    assert (await c["A"].get("/api/v1/discovery/players")).status_code == 503
    assert (await call("A", "/blocks/" + a["B"]["handle"])).status_code == 503


async def test_reads_create_no_sync_work_and_private_report_is_not_readable(social):
    auth, c, a, ids, call, send = social
    async with auth.resources.sessions() as db:
        before = await db.scalar(select(func.count()).select_from(SyncJob))
    for route in [
        "/users/search?q=abc",
        "/discovery/players",
        "/discovery/steam-friends",
        "/connections",
        "/connection-requests/incoming",
        "/connection-requests/outgoing",
        "/blocks",
        "/notifications",
    ]:
        assert (await c["A"].get("/api/v1" + route)).status_code == 200
    assert (await c["A"].get("/api/v1/reports")).status_code == 405
    async with auth.resources.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(SyncJob)) == before


@pytest.mark.parametrize("model", ["connection", "block", "pending"])
async def test_database_constraints_independent_of_service(social, model):
    auth, c, a, ids, call, send = social
    lo, hi = pair(ids["A"], ids["B"])
    async with auth.resources.sessions() as db:
        with pytest.raises(IntegrityError):
            async with db.begin():
                if model == "connection":
                    db.add(Connection(user_id_low=hi, user_id_high=lo))
                elif model == "block":
                    db.add(UserBlock(blocker_id=lo, blocked_id=lo))
                else:
                    for sender, receiver in [(lo, hi), (hi, lo)]:
                        db.add(
                            ConnectionRequest(
                                sender_id=sender,
                                receiver_id=receiver,
                                user_id_low=lo,
                                user_id_high=hi,
                                expires_at=utcnow() + timedelta(days=1),
                            )
                        )
                await db.flush()


@pytest.mark.parametrize("category,limit", [("requests", 10), ("blocks", 30), ("discovery", 15)])
async def test_abuse_limits_apply_even_to_retries(social, category, limit):
    auth, c, a, ids, call, send = social

    async def operation():
        if category == "requests":
            return await call("A", "/connection-requests", body={"handle": a["B"]["handle"]})
        if category == "blocks":
            return await call("A", "/blocks/" + a["B"]["handle"])
        return await c["A"].get("/api/v1/discovery/players")

    for _ in range(limit):
        assert (await operation()).status_code in {200, 204}
    response = await operation()
    assert response.status_code == 429 and response.headers["retry-after"] == "60"
    if category == "requests":
        assert (await counts(auth, ids))["notifications"] == 1


async def test_private_connection_can_be_blocked_and_report_survives_removal(social):
    auth, c, a, ids, call, send = social
    rid = await send()
    await call("B", f"/connection-requests/{rid}/accept")
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(
            update(PrivacySettings)
            .where(PrivacySettings.user_id == ids["B"])
            .values(profile="private")
        )
    receipt = await call("A", "/reports", body={"handle": a["B"]["handle"], "reason": "spam"})
    assert receipt.status_code == 200
    assert (await call("A", "/blocks/" + a["B"]["handle"])).status_code == 204
    async with auth.resources.sessions() as db:
        assert await db.get(UserReport, UUID(receipt.json()["id"]))
    assert (await counts(auth, ids))["connections"] == 0


async def test_all_connections_only_resources_and_search_transition_immediately(social):
    auth, c, a, ids, call, send = social
    rid = await send()
    await call("B", f"/connection-requests/{rid}/accept")
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(
            update(PrivacySettings)
            .where(PrivacySettings.user_id == ids["B"])
            .values(
                profile="connections",
                library="connections",
                playtime="connections",
                achievements="connections",
            )
        )
    path = "/api/v1/users/" + a["B"]["handle"]
    view = (await c["A"].get(path)).json()
    assert view["game_count"] == 3 and view["playtime_visible"] and view["achievements_visible"]
    assert (await c["C"].get(path)).status_code == 404
    assert (
        len(
            (await c["A"].get("/api/v1/users/search", params={"q": a["B"]["handle"]})).json()[
                "items"
            ]
        )
        == 1
    )
    assert (await call("A", "/connections/" + a["B"]["handle"], "DELETE")).status_code == 204
    assert (await c["A"].get(path)).status_code == 404
    assert (await c["A"].get("/api/v1/users/search", params={"q": a["B"]["handle"]})).json()[
        "items"
    ] == []
    assert a["B"]["handle"] not in (await c["A"].get("/api/v1/discovery/players")).text


async def test_reporter_deletion_also_redacts_description(social):
    auth, c, a, ids, call, send = social
    receipt = await call(
        "A",
        "/reports",
        body={
            "handle": a["B"]["handle"],
            "reason": "other",
            "description": "Reporter personal content",
        },
    )
    assert (await call("A", "/me", "DELETE", {"confirmation": "DELETE"})).status_code == 204
    async with auth.resources.sessions() as db:
        row = await db.get(UserReport, UUID(receipt.json()["id"]))
        assert row.reporter_id is None and row.description == "" and row.target_id == ids["B"]
