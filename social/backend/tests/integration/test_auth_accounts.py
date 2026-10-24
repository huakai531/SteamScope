import asyncio
from datetime import timedelta
from uuid import UUID

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from steamscope_social.core.database import utcnow
from steamscope_social.core.models import (
    AuditLog,
    LoginAttempt,
    PrivacySettings,
    SteamAccount,
    User,
    UserSession,
)
from steamscope_social.modules.administration.cleanup import purge_expired
from steamscope_social.modules.auth.security import digest, session_cookie
from tests.provider_fixtures import assertion

pytestmark = pytest.mark.integration


async def test_driver_connection_failure_is_safe_service_unavailable(auth, monkeypatch):
    from steamscope_social.api import account

    async def unavailable(*args):
        raise ConnectionRefusedError("PRIVATE_DATABASE_CONNECTION")

    monkeypatch.setattr(account, "prepare_attempt", unavailable)
    client = await auth.client()
    response = await client.get("/api/v1/auth/steam/login")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert "PRIVATE_DATABASE_CONNECTION" not in response.text
    assert not response.headers.get_list("set-cookie")


async def test_current_logout_invalidates_copied_credential_and_pending_attempt(auth):
    client = await auth.client()
    identity = auth.identity()
    await auth.login(client, identity)
    pending = assertion(await auth.start(client), identity)
    stale = await auth.client()
    stale.cookies.set(session_cookie(auth.config), client.cookies[session_cookie(auth.config)])
    response = await client.post("/api/v1/auth/logout", headers=await auth.headers(client))
    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert (await stale.get("/api/v1/me")).status_code == 401
    assert (
        "LOGIN_FAILED"
        in (await client.get("/api/v1/auth/steam/callback", params=pending)).headers["location"]
    )


async def test_sensitive_callback_and_exception_data_are_not_logged(auth, monkeypatch):
    import io
    import logging

    from steamscope_social.api import account
    from steamscope_social.core.logging import JsonFormatter

    client = await auth.client()
    params = assertion(await auth.start(client), auth.identity())
    captured = io.StringIO()
    handler = logging.StreamHandler(captured)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("steamscope_social")
    logger.addHandler(handler)

    async def failure(*args):
        raise RuntimeError("SECRET_EXCEPTION " + params["openid.sig"])

    monkeypatch.setattr(account, "verify_assertion", failure)
    try:
        response = await client.get("/api/v1/auth/steam/callback", params=params)
        assert response.headers["location"].endswith("/login?error=LOGIN_FAILED")
        assert "request_failed:" in captured.getvalue()
        for secret in [
            params["state"],
            params["openid.sig"],
            params["openid.claimed_id"],
            "SECRET_EXCEPTION",
            "openid.",
            "Cookie",
        ]:
            assert secret not in captured.getvalue() and secret not in response.text
    finally:
        logger.removeHandler(handler)


async def test_first_returning_login_rotation_and_digest_only(auth):
    client = await auth.client()
    identity = auth.identity()
    first = await auth.login(client, identity)
    cookie_name = session_cookie(auth.config)
    old_token = client.cookies[cookie_name]
    assert first["steam_id"] == identity and first["steam_data_synchronized"] is False
    response = await client.patch(
        "/api/v1/me",
        json={"display_name": "Chosen name", "biography": "plain <text>"},
        headers=await auth.headers(client),
    )
    assert response.status_code == 200
    second = await auth.login(client, identity)
    assert first["id"] == second["id"] and second["display_name"] == "Chosen name"
    assert client.cookies[cookie_name] != old_token
    old = await auth.client()
    old.cookies.set(cookie_name, old_token)
    assert (await old.get("/api/v1/me")).status_code == 401
    async with auth.resources.sessions() as db:
        sessions = (
            await db.scalars(select(UserSession).where(UserSession.user_id == UUID(first["id"])))
        ).all()
        assert all(
            len(row.token_digest) == 64
            and row.token_digest not in {old_token, client.cookies[cookie_name]}
            for row in sessions
        )
    metadata = await client.get("/api/v1/me/sessions")
    assert metadata.status_code == 200 and "token_digest" not in metadata.text
    assert "no-store" in metadata.headers["cache-control"]


async def test_cookie_scope_and_parallel_tab_transactions(auth):
    client = await auth.client()
    one, two = await auth.start(client), await auth.start(client)
    identity = auth.identity()
    first = await client.get("/api/v1/auth/steam/callback", params=assertion(one, identity))
    cookies = first.headers.get_list("set-cookie")
    assert len(cookies) == 2 and all(
        "HttpOnly" in item and "SameSite=lax" in item for item in cookies
    )
    assert any("Path=/;" in item for item in cookies)
    second = await client.get("/api/v1/auth/steam/callback", params=assertion(two, identity))
    assert second.headers["location"].endswith("/account")


@pytest.mark.parametrize(
    "mode",
    [
        "cancel",
        "bad-provider",
        "bad-signature",
        "timeout",
        "malformed",
        "duplicate",
        "expired",
        "browser-mismatch",
    ],
)
async def test_failed_verification_never_creates_accounts_or_sessions(auth, mode):
    client = await auth.client()
    other = await auth.client()
    identity = auth.identity()
    url = await auth.start(client)
    params = assertion(url, identity)
    if mode == "cancel":
        params["openid.mode"] = "cancel"
    if mode == "bad-provider":
        params["openid.op_endpoint"] = "https://attacker.invalid"
    if mode == "bad-signature":
        params["openid.sig"] = "eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4"
    if mode == "timeout":
        auth.provider.failure = "timeout"
    if mode == "malformed":
        auth.provider.verification = "is_valid:true\n"
    if mode == "expired":
        async with auth.resources.sessions() as db, db.begin():
            await db.execute(
                update(LoginAttempt)
                .where(LoginAttempt.state_digest == digest(params["state"]))
                .values(
                    created_at=utcnow() - timedelta(hours=1),
                    expires_at=utcnow() - timedelta(minutes=1),
                )
            )
    pairs = list(params.items()) + ([("openid.mode", "cancel")] if mode == "duplicate" else [])
    response = await (other if mode == "browser-mismatch" else client).get(
        "/api/v1/auth/steam/callback", params=pairs
    )
    assert "/login?error=" in response.headers["location"]
    assert (await client.get("/api/v1/me")).status_code == 401
    async with auth.resources.sessions() as db:
        assert (
            await db.scalar(select(SteamAccount).where(SteamAccount.steam_id == identity)) is None
        )
    if mode == "browser-mismatch":
        # A wrong browser cannot consume the rightful browser's transaction.
        valid = await client.get("/api/v1/auth/steam/callback", params=params)
        assert valid.headers["location"].endswith("/account")


async def test_replayed_attempt_and_nonce_are_rejected(auth):
    client = await auth.client()
    identity = auth.identity()
    params = assertion(await auth.start(client), identity)
    cookies = list(client.cookies.jar)
    assert (
        (await client.get("/api/v1/auth/steam/callback", params=params))
        .headers["location"]
        .endswith("/account")
    )
    for cookie in cookies:
        client.cookies.jar.set_cookie(cookie)
    replay = await client.get("/api/v1/auth/steam/callback", params=params)
    assert "LOGIN_FAILED" in replay.headers["location"]
    fresh = assertion(
        await auth.start(client),
        identity,
        **{"openid.response_nonce": params["openid.response_nonce"]},
    )
    assert (
        "LOGIN_FAILED"
        in (await client.get("/api/v1/auth/steam/callback", params=fresh)).headers["location"]
    )


async def test_concurrent_first_login_has_no_duplicate_or_orphan_user(auth):
    identity = auth.identity()
    clients = [await auth.client() for _ in range(4)]
    starts = [await auth.start(client) for client in clients]
    async with auth.resources.sessions() as db:
        before = await db.scalar(select(func.count()).select_from(User))
    results = await asyncio.gather(
        *(
            client.get("/api/v1/auth/steam/callback", params=assertion(url, identity))
            for client, url in zip(clients, starts, strict=True)
        )
    )
    assert all(row.headers["location"].endswith("/account") for row in results)
    ids = {(await client.get("/api/v1/me")).json()["id"] for client in clients}
    assert len(ids) == 1
    async with auth.resources.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(User)) == before + 1
        assert (
            await db.scalar(
                select(func.count())
                .select_from(PrivacySettings)
                .where(PrivacySettings.user_id == UUID(next(iter(ids))))
            )
            == 1
        )


async def test_uniqueness_constraints_rollback_and_handle_collision(auth, monkeypatch):
    from steamscope_social.modules.auth import service

    client = await auth.client()
    user = await auth.login(client)
    assert (
        await client.patch(
            "/api/v1/me",
            json={"handle": "Case" + user["id"][:8]},
            headers=await auth.headers(client),
        )
    ).status_code == 200
    other = await auth.client()
    second = await auth.login(other)
    response = await other.patch(
        "/api/v1/me",
        json={"handle": ("Case" + user["id"][:8]).upper()},
        headers=await auth.headers(other),
    )
    assert response.status_code == 409
    assert (await other.get("/api/v1/me")).json()["handle"] == second["handle"]
    handles = iter(["Case" + user["id"][:8], "safe_" + user["id"][:8]])
    monkeypatch.setattr(service, "initial_handle", lambda: next(handles))
    third = await auth.login(await auth.client())
    assert third["handle"].startswith("safe_")
    async with auth.resources.sessions() as db:
        before = await db.scalar(select(func.count()).select_from(User))
    # Deliberate unique-link failure inside a transaction must roll back the new user too.
    with pytest.raises(IntegrityError):
        async with auth.resources.sessions() as db, db.begin():
            orphan = User(handle="orphan_" + user["id"][:8], display_name="Rollback fixture")
            db.add(orphan)
            await db.flush()
            db.add(SteamAccount(user_id=orphan.id, steam_id=user["steam_id"]))
            await db.flush()
    async with auth.resources.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(User)) == before


async def test_session_expiry_idle_disabled_and_owned_revocation(auth):
    identity = auth.identity()
    first, second, stranger = await auth.client(), await auth.client(), await auth.client()
    account = await auth.login(first, identity)
    await auth.login(second, identity)
    await auth.login(stranger)
    current = next(
        item for item in (await second.get("/api/v1/me/sessions")).json() if item["current"]
    )
    assert (
        await stranger.delete(
            "/api/v1/me/sessions/" + current["id"], headers=await auth.headers(stranger)
        )
    ).status_code == 404
    assert (
        await first.delete(
            "/api/v1/me/sessions/" + current["id"], headers=await auth.headers(first)
        )
    ).status_code == 204
    assert (await second.get("/api/v1/me")).status_code == 401
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(
            update(UserSession)
            .where(UserSession.user_id == UUID(account["id"]))
            .values(last_seen_at=utcnow() - timedelta(days=2))
        )
    assert (await first.get("/api/v1/me")).status_code == 401
    await auth.login(first, identity)
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(
            update(UserSession)
            .where(UserSession.user_id == UUID(account["id"]))
            .values(
                created_at=utcnow() - timedelta(days=2), expires_at=utcnow() - timedelta(days=1)
            )
        )
    assert (await first.get("/api/v1/me")).status_code == 401
    await auth.login(first, identity)
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(
            update(User).where(User.id == UUID(account["id"])).values(status="disabled")
        )
    assert (await first.get("/api/v1/me")).status_code == 401


async def test_csrf_origin_mass_assignment_privacy_and_logout_all(auth):
    client, other = await auth.client(), await auth.client()
    identity = auth.identity()
    assert (await client.get("/api/v1/me")).status_code == 401
    await auth.login(client, identity)
    await auth.login(other, identity)
    assert (await client.patch("/api/v1/me", json={"display_name": "x"})).status_code == 403
    headers = await auth.headers(client)
    assert (
        await client.patch(
            "/api/v1/me",
            json={"display_name": "x"},
            headers={**headers, "Origin": "http://localhost:3100"},
        )
    ).status_code == 403
    assert (
        await client.patch(
            "/api/v1/me", json={"display_name": "x"}, headers={**headers, "X-CSRF-Token": "bad"}
        )
    ).status_code == 403
    for field in ["id", "steam_id", "status", "roles"]:
        assert (
            await client.patch("/api/v1/me", json={field: "changed"}, headers=headers)
        ).status_code == 422
    privacy = (await client.get("/api/v1/me/privacy")).json()
    assert privacy == {
        "profile": "private",
        "library": "private",
        "playtime": "private",
        "achievements": "private",
        "presence": "private",
        "discovery": False,
        "connection_requests": "nobody",
        "messaging": "nobody",
    }
    assert (
        await client.patch("/api/v1/me/privacy", json={"discovery": True}, headers=headers)
    ).json()["discovery"] is True
    assert (
        await client.patch("/api/v1/me/privacy", json={"user_id": "foreign"}, headers=headers)
    ).status_code == 422
    assert (await client.post("/api/v1/auth/logout-all", headers=headers)).status_code == 204
    assert (await client.get("/api/v1/me")).status_code == 401
    assert (await other.get("/api/v1/me")).status_code == 401


async def test_recent_reauth_wrong_identity_and_deletion_erasure(auth):
    client = await auth.client()
    identity = auth.identity()
    account = await auth.login(client, identity)
    user_id = UUID(account["id"])
    pending = assertion(await auth.start(client), identity)
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id)
            .values(authenticated_at=utcnow() - timedelta(hours=1))
        )
    headers = await auth.headers(client)
    assert (
        await client.request(
            "DELETE", "/api/v1/me", json={"confirmation": "DELETE"}, headers=headers
        )
    ).json()["error"]["code"] == "REAUTH_REQUIRED"
    wrong = assertion(await auth.start(client, reauth=True), auth.identity())
    assert (
        "REAUTH_IDENTITY_MISMATCH"
        in (await client.get("/api/v1/auth/steam/callback", params=wrong)).headers["location"]
    )
    assert (await client.get("/api/v1/me")).json()["id"] == account["id"]
    correct = assertion(await auth.start(client, reauth=True), identity)
    assert (
        (await client.get("/api/v1/auth/steam/callback", params=correct))
        .headers["location"]
        .endswith("/account/delete")
    )
    headers = await auth.headers(client)
    assert (
        await client.request(
            "DELETE", "/api/v1/me", json={"confirmation": "wrong"}, headers=headers
        )
    ).status_code == 422
    token = client.cookies[session_cookie(auth.config)]
    assert (
        await client.request(
            "DELETE", "/api/v1/me", json={"confirmation": "DELETE"}, headers=headers
        )
    ).status_code == 204
    assert (
        "LOGIN_FAILED"
        in (await client.get("/api/v1/auth/steam/callback", params=pending)).headers["location"]
    )
    stale = await auth.client()
    stale.cookies.set(session_cookie(auth.config), token)
    assert (await stale.get("/api/v1/me")).status_code == 401
    async with auth.resources.sessions() as db:
        assert await db.get(User, user_id) is None
        for model in [SteamAccount, PrivacySettings, UserSession]:
            assert (
                await db.scalar(
                    select(func.count()).select_from(model).where(model.user_id == user_id)
                )
                == 0
            )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(LoginAttempt)
                .where(LoginAttempt.bound_user_id == user_id)
            )
            == 0
        )
        assert (
            await db.scalar(
                select(func.count()).select_from(AuditLog).where(AuditLog.actor_id == user_id)
            )
            == 0
        )
    new_account = await auth.login(client, identity)
    assert new_account["id"] != account["id"] and new_account["display_name"] == "New player"


async def test_rate_limiting_dependency_outage_and_retention(auth, monkeypatch):
    from unittest.mock import AsyncMock

    client = await auth.client()
    auth.config.auth_rate_limit = 1
    first = await auth.start(client)
    assert (await client.get("/api/v1/auth/steam/login")).status_code == 429
    auth.config.auth_rate_limit = 1000
    identity = auth.identity()
    monkeypatch.setattr(
        auth.resources.redis,
        "eval",
        AsyncMock(side_effect=RedisConnectionError("SECRET_REDIS_ENDPOINT")),
    )
    failed = await client.get("/api/v1/auth/steam/callback", params=assertion(first, identity))
    assert "AUTH_DEPENDENCY_UNAVAILABLE" in failed.headers["location"]
    assert "SECRET_REDIS_ENDPOINT" not in failed.text
    monkeypatch.undo()
    await auth.login(client, identity)
    auth.config.sensitive_rate_limit = 1
    headers = await auth.headers(client)
    assert (
        await client.patch("/api/v1/me", json={"display_name": "ok"}, headers=headers)
    ).status_code == 200
    assert (
        await client.patch("/api/v1/me", json={"display_name": "again"}, headers=headers)
    ).status_code == 429
    async with auth.resources.sessions() as db, db.begin():
        old = AuditLog(event="expired_test", created_at=utcnow() - timedelta(days=91))
        new = AuditLog(event="recent_test")
        db.add_all([old, new])
        await db.flush()
        old_id, new_id = old.id, new.id
        await purge_expired(db, auth.config)
        assert await db.get(AuditLog, old_id) is None
        assert await db.get(AuditLog, new_id) is not None
        await db.execute(delete(AuditLog).where(AuditLog.id == new_id))
