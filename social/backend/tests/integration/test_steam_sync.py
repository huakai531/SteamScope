import asyncio
from datetime import timedelta
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import func, select, update

from steamscope_social.core.database import utcnow
from steamscope_social.modules.auth.models import SteamAccount
from steamscope_social.modules.steam.client import Snapshot, SteamClient
from steamscope_social.modules.steam.jobs import (
    begin_resource,
    claim_next,
    process_claim,
    save_resource,
)
from steamscope_social.modules.steam.models import (
    RecentGame,
    RequestBudget,
    SyncJob,
    SyncState,
    UserGame,
)
from tests.steam_fixtures import KEY, transport

pytestmark = pytest.mark.integration
BASE = "/api/v1/me/steam"


@pytest.fixture
async def steam(auth):
    auth.config.steam_api_key = SecretStr(KEY)
    # Production caps remain validated; deterministic tests use an isolated DB and larger budgets.
    auth.config.steam_requests_per_minute = 100000
    auth.config.steam_requests_per_day = 100000
    client = await auth.client()
    account = await auth.login(client)
    return auth, client, UUID(account["id"])


async def queue(auth, client):
    response = await client.post(BASE + "/sync", headers=await auth.headers(client))
    assert response.status_code == 202, response.text
    return response.json()["job"]["id"]


async def work(auth, handler=transport):
    claim = await claim_next(auth.resources, auth.config)
    assert claim is not None
    await process_claim(
        auth.resources, auth.config, SteamClient(auth.config, httpx.MockTransport(handler)), claim
    )
    return claim


async def make_due(auth, user_id):
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(
            update(SyncJob)
            .where(SyncJob.user_id == user_id)
            .values(
                available_at=utcnow() - timedelta(seconds=1),
                created_at=utcnow() - timedelta(minutes=10),
            )
        )


async def test_pipeline_pagination_persona_preservation_dedup_and_cooldown(steam):
    auth, client, user_id = steam
    await client.patch(
        "/api/v1/me",
        headers=await auth.headers(client),
        json={"display_name": "My chosen name", "biography": "Preserve me"},
    )
    job = await queue(auth, client)
    duplicate = await client.post(BASE + "/sync", headers=await auth.headers(client))
    assert duplicate.status_code == 200 and duplicate.json()["job"]["id"] == job
    assert (await client.get(BASE + "/sync-status")).json()["resources"][0]["in_progress"]
    await work(auth)
    assert (await client.get("/api/v1/me")).json()["steam_data_synchronized"] is True
    assert (await client.get(BASE + "/sync-jobs/" + job)).json()["job"]["status"] == "succeeded"
    assert (await client.get("/api/v1/me")).json()["display_name"] == "My chosen name"
    assert (await client.get(BASE + "/profile")).json()["persona_name"] == "Synthetic Steam persona"
    page = (await client.get(BASE + "/games?limit=25")).json()
    assert len(page["items"]) == 25 and page["returned_game_count"] == 27
    assert page["items"][0]["total_minutes"] == 0
    assert page["total_minutes"] == sum(i * 61 for i in range(27))
    second = (
        await client.get(
            BASE + f"/games?after={page['next_after']}&snapshot={page['state']['snapshot_id']}"
        )
    ).json()
    assert len(second["items"]) == 2
    assert (
        await client.post(BASE + "/sync", headers=await auth.headers(client))
    ).status_code == 429
    assert len((await client.get(BASE + "/recent-games")).json()["items"]) == 1
    await make_due(auth, user_id)
    await queue(auth, client)
    await work(auth)
    stale_page = await client.get(
        BASE + f"/games?after={page['next_after']}&snapshot={page['state']['snapshot_id']}"
    )
    assert stale_page.status_code == 409
    async with auth.resources.sessions() as db:
        assert (
            await db.scalar(
                select(func.count()).select_from(UserGame).where(UserGame.user_id == user_id)
            )
            == 27
        )


async def test_owner_authorization_csrf_missing_key_and_confirmed_clear(steam):
    auth, client, user_id = steam
    anonymous = await auth.client()
    for path in ("/sync-status", "/profile", "/games", "/recent-games"):
        assert (await anonymous.get(BASE + path)).status_code == 401
    assert (await client.post(BASE + "/sync")).status_code == 403
    auth.config.steam_api_key = SecretStr("")
    status = (await client.get(BASE + "/sync-status")).json()
    assert (
        status["capability"] == "unconfigured"
        and "SOCIAL_STEAM_API_KEY" in status["operator_instruction"]
    )
    assert (
        await client.post(BASE + "/sync", headers=await auth.headers(client))
    ).status_code == 503
    assert (await client.get("/health/ready")).status_code == 200
    auth.config.steam_api_key = SecretStr(KEY)
    job = await queue(auth, client)
    other = await auth.client()
    await auth.login(other)
    assert (await other.get(BASE + "/sync-jobs/" + job)).status_code == 404
    await work(auth)
    assert (await other.get(BASE + "/games")).json()["returned_game_count"] is None
    assert (
        await client.request(
            "DELETE",
            BASE + "/data",
            headers=await auth.headers(client),
            json={"confirmation": "wrong"},
        )
    ).status_code == 422
    assert (
        await client.request(
            "DELETE",
            BASE + "/data",
            headers=await auth.headers(client),
            json={"confirmation": "CLEAR STEAM DATA"},
        )
    ).status_code == 204
    assert (await client.get(BASE + "/games")).json()["state"]["status"] == "never"
    assert (await client.get(BASE + "/profile")).json()["persona_name"] is None
    assert (await client.get("/api/v1/me")).status_code == 200
    assert await claim_next(auth.resources, auth.config) is None


async def test_partial_retries_preserve_success_and_terminal_bound(steam):
    auth, client, user_id = steam
    job = await queue(auth, client)
    calls = []

    def partial(request):
        calls.append(request.url.path)
        return httpx.Response(503) if "GetOwnedGames" in request.url.path else transport(request)

    for _attempt in range(3):
        await work(auth, partial)
        await make_due(auth, user_id)
    result = (await client.get(BASE + "/sync-jobs/" + job)).json()
    assert result["job"]["status"] == "partial" and result["job"]["attempts"] == 3
    assert len(result["runs"]) == 3 and len(calls) == 5
    assert (await client.get(BASE + "/profile")).json()["state"]["data_available"]
    assert (await client.get(BASE + "/games")).json()["returned_game_count"] is None
    assert await claim_next(auth.resources, auth.config) is None


@pytest.mark.parametrize(
    "response,expected,visible",
    [
        (httpx.Response(500), "retry", True),
        (httpx.Response(200, text="invalid json"), "error", True),
        (httpx.Response(200, json={"response": {}}), "unknown", False),
        (httpx.Response(403), "unavailable", False),
    ],
)
async def test_failed_or_ambiguous_fetch_never_erases_library(steam, response, expected, visible):
    auth, client, user_id = steam
    await queue(auth, client)
    await work(auth)
    previous = (await client.get(BASE + "/games")).json()["state"]["last_success_at"]
    await make_due(auth, user_id)
    await queue(auth, client)
    await work(auth, lambda r: response if "GetOwnedGames" in r.url.path else transport(r))
    result = (await client.get(BASE + "/games")).json()
    assert result["state"]["status"] == expected
    assert result["state"]["last_success_at"] == previous and result["state"]["stale"]
    assert result["state"]["data_available"] is visible
    assert (result["returned_game_count"] == 27) is visible
    async with auth.resources.sessions() as db:
        assert (
            await db.scalar(
                select(func.count()).select_from(UserGame).where(UserGame.user_id == user_id)
            )
            == 27
        )


async def test_profile_restriction_does_not_infer_library_and_recent_rollover(steam):
    auth, client, user_id = steam
    await queue(auth, client)
    await work(auth)
    async with auth.resources.sessions() as db, db.begin():
        state = await db.get(SyncState, (user_id, "recent"))
        state.last_success_at = utcnow() - timedelta(minutes=16)
    old = (await client.get(BASE + "/recent-games")).json()
    assert old["state"]["stale"] and old["items"] == [] and old["returned_game_count"] is None
    await make_due(auth, user_id)
    await queue(auth, client)

    def changed(request):
        if "GetPlayerSummaries" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "response": {
                        "players": [
                            {
                                "steamid": request.url.params["steamids"],
                                "communityvisibilitystate": 1,
                            }
                        ]
                    }
                },
            )
        if "GetRecentlyPlayedGames" in request.url.path:
            return httpx.Response(200, json={"response": {"total_count": 0}})
        return transport(request)

    await work(auth, changed)
    assert (await client.get(BASE + "/profile")).json()["state"]["status"] == "restricted"
    assert (await client.get(BASE + "/games")).json()["returned_game_count"] == 27
    recent = (await client.get(BASE + "/recent-games")).json()
    assert recent["returned_game_count"] == 0 and recent["state"]["status"] == "empty"
    async with auth.resources.sessions() as db:
        assert (
            await db.scalar(
                select(func.count()).select_from(RecentGame).where(RecentGame.user_id == user_id)
            )
            == 0
        )


async def test_two_claimers_lease_recovery_and_stale_writer_fenced(steam):
    auth, client, user_id = steam
    await queue(auth, client)
    claims = await asyncio.gather(
        claim_next(auth.resources, auth.config), claim_next(auth.resources, auth.config)
    )
    assert sum(c is not None for c in claims) == 1
    old = next(c for c in claims if c)
    assert await begin_resource(auth.resources, auth.config, old, "profile") == 0
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(
            update(SyncJob)
            .where(SyncJob.id == old.job_id)
            .values(lease_until=utcnow() - timedelta(seconds=1))
        )
    new = await claim_next(auth.resources, auth.config)
    assert new and new.token != old.token and new.attempts == 2
    await process_claim(
        auth.resources, auth.config, SteamClient(auth.config, httpx.MockTransport(transport)), new
    )
    assert not await save_resource(
        auth.resources, old, "profile", Snapshot("populated", "OK", persona="STALE")
    )
    assert (await client.get(BASE + "/profile")).json()["persona_name"] == "Synthetic Steam persona"


@pytest.mark.parametrize("deleting", [False, True])
async def test_inflight_response_cannot_resurrect_clear_or_deleted_account(steam, deleting):
    auth, client, user_id = steam
    await queue(auth, client)
    claimed = await claim_next(auth.resources, auth.config)
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed(request):
        entered.set()
        await release.wait()
        return transport(request)

    task = asyncio.create_task(
        process_claim(
            auth.resources,
            auth.config,
            SteamClient(auth.config, httpx.MockTransport(delayed)),
            claimed,
        )
    )
    await asyncio.wait_for(entered.wait(), 5)
    target = "/api/v1/me" if deleting else BASE + "/data"
    confirmation = "DELETE" if deleting else "CLEAR STEAM DATA"
    response = await client.request(
        "DELETE", target, headers=await auth.headers(client), json={"confirmation": confirmation}
    )
    assert response.status_code == 204, response.text
    release.set()
    await asyncio.wait_for(task, 5)
    async with auth.resources.sessions() as db:
        assert (
            await db.scalar(
                select(func.count()).select_from(UserGame).where(UserGame.user_id == user_id)
            )
            == 0
        )
        assert (
            await db.scalar(
                select(func.count()).select_from(SyncState).where(SyncState.user_id == user_id)
            )
            == 0
        )
        link = await db.scalar(select(SteamAccount).where(SteamAccount.user_id == user_id))
        assert (link is None) is deleting
    assert await claim_next(auth.resources, auth.config) is None


async def test_persistent_per_user_request_budget_and_recent_auth_clear(steam):
    auth, client, user_id = steam
    from steamscope_social.modules.auth.models import UserSession
    from steamscope_social.modules.steam.jobs import budget

    auth.config.steam_user_requests_per_hour = 3
    async with auth.resources.sessions() as db, db.begin():
        assert [await budget(db, user_id, auth.config) for _ in range(3)] == [0, 0, 0]
    async with auth.resources.sessions() as db, db.begin():
        assert await budget(db, user_id, auth.config) > 0
        assert (await db.get(RequestBudget, ("user", str(user_id)))).used == 3
        await db.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id)
            .values(authenticated_at=utcnow() - timedelta(hours=1))
        )
    assert (
        await client.request(
            "DELETE",
            BASE + "/data",
            headers=await auth.headers(client),
            json={"confirmation": "CLEAR STEAM DATA"},
        )
    ).status_code == 403


async def test_independent_worker_kill_and_restart_recovers_persisted_job(steam):
    import os
    import subprocess
    import sys
    from pathlib import Path

    auth, client, user_id = steam
    job_id = await queue(auth, client)
    env = dict(
        os.environ,
        SOCIAL_STEAM_API_KEY=KEY,
        SOCIAL_STEAM_REQUESTS_PER_MINUTE="60",
        SOCIAL_STEAM_REQUESTS_PER_DAY="10000",
    )
    script = (await asyncio.to_thread(Path(__file__).resolve)).parents[
        1
    ] / "steam_worker_process.py"
    child = await asyncio.to_thread(
        subprocess.Popen,
        [sys.executable, str(script), "--pause"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        marker = await asyncio.wait_for(asyncio.to_thread(child.stdout.readline), 8)
        assert marker.strip() == "IN_FLIGHT_AFTER_COMMITTED_CLAIM"
        child.kill()
        await asyncio.to_thread(child.wait, timeout=5)
        async with auth.resources.sessions() as db, db.begin():
            job = await db.get(SyncJob, UUID(job_id))
            assert job.status == "running" and job.attempts == 1
            job.lease_until = utcnow() - timedelta(
                seconds=1
            )  # expedite lease clock on disposable data
        result = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, str(script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, "Isolated worker restart failed; no raw error output"
        assert "PROCESSED_PERSISTED_JOB" in result.stdout
        saved = (await client.get(BASE + "/sync-jobs/" + job_id)).json()
        assert saved["job"]["status"] == "succeeded" and saved["job"]["attempts"] == 2
        assert saved["runs"][0]["status"] == "lease_expired"
        assert (await client.get(BASE + "/games")).json()["returned_game_count"] == 27
    finally:
        if child.poll() is None:
            child.kill()
            await asyncio.to_thread(child.wait, timeout=5)


async def test_graceful_cancellation_releases_claim_for_bounded_retry(steam):
    auth, client, user_id = steam
    job = await queue(auth, client)
    claim = await claim_next(auth.resources, auth.config)
    entered = asyncio.Event()

    async def waiting(request):
        entered.set()
        await asyncio.sleep(60)
        return transport(request)

    task = asyncio.create_task(
        process_claim(
            auth.resources,
            auth.config,
            SteamClient(auth.config, httpx.MockTransport(waiting)),
            claim,
        )
    )
    await asyncio.wait_for(entered.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    saved = (await client.get(BASE + "/sync-jobs/" + job)).json()
    assert saved["job"]["status"] == "retry" and saved["runs"][0]["status"] == "interrupted"


async def test_retry_after_is_shared_and_persisted_across_resource_instances(steam):
    from steamscope_social.core.resources import Resources
    from steamscope_social.modules.steam.jobs import budget

    auth, client, user_id = steam
    await queue(auth, client)
    claim = await claim_next(auth.resources, auth.config)
    assert await begin_resource(auth.resources, auth.config, claim, "profile") == 0
    async with auth.resources.sessions() as db:
        previous = (await db.get(RequestBudget, ("day", "shared"))).blocked_until
    another = Resources(auth.config)
    try:
        assert await save_resource(
            auth.resources, claim, "profile", Snapshot("retry", "UPSTREAM_RATE_LIMIT", 120)
        )
        async with another.sessions() as db, db.begin():
            assert await budget(db, user_id, auth.config) >= 119
            row = await db.get(RequestBudget, ("day", "shared"))
            assert row.blocked_until > utcnow() + timedelta(seconds=115)
    finally:
        # Only restores this test's change to a counter in the explicitly isolated test DB.
        async with auth.resources.sessions() as db, db.begin():
            await db.execute(
                update(RequestBudget)
                .where(RequestBudget.scope == "day", RequestBudget.owner == "shared")
                .values(blocked_until=previous)
            )
        await another.close()
