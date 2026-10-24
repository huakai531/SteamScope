import asyncio
from datetime import timedelta
from uuid import UUID

import httpx
import pytest
from sqlalchemy import delete, func, select, update

from steamscope_social.core.database import utcnow
from steamscope_social.modules.steam.client import SteamClient
from steamscope_social.modules.steam.jobs import claim_next, process_claim
from steamscope_social.modules.steam.models import (
    AchievementSchema,
    AchievementState,
    RequestBudget,
    SteamFriend,
    SyncJob,
    SyncState,
    UserAchievement,
)
from steamscope_social.modules.users.models import User
from tests.integration.test_steam_sync import make_due, queue, work
from tests.integration.test_steam_sync import steam as steam
from tests.steam_details_fixtures import friends_payload, player_payload, schema_payload, transport
from tests.steam_fixtures import APP

pytestmark = pytest.mark.integration
BASE = "/api/v1/me/steam"
ACH = f"/games/{APP}/achievements"


@pytest.fixture
async def details(steam):
    auth, client, owner = steam
    auth.config.steam_user_requests_per_hour = 100000
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(
            delete(AchievementSchema).where(AchievementSchema.app_id.between(APP, APP + 26))
        )
    await queue(auth, client)
    await work(auth)
    try:
        yield auth, client, owner
    finally:
        async with auth.resources.sessions() as db, db.begin():
            await db.execute(
                delete(AchievementSchema).where(AchievementSchema.app_id.between(APP, APP + 26))
            )


async def sync(auth, client, path=ACH, handler=transport):
    response = await client.post(BASE + path + "/sync", headers=await auth.headers(client))
    assert response.status_code == 202, response.text
    await work(auth, handler)
    return (await client.get(BASE + "/sync-jobs/" + response.json()["job"]["id"])).json()


async def test_denied_player_evidence_is_bound_to_run_without_changing_schema_or_friends(details):
    auth, client, owner = details
    calls = []

    def denied(request):
        calls.append(request.url.path)
        if "GetPlayerAchievements" in request.url.path:
            return httpx.Response(
                403, json={"playerstats": {"success": False, "error": "Profile is not public"}}
            )
        return transport(request)

    task = await sync(auth, client, handler=denied)
    assert len(calls) == 2 and task["job"]["status"] == "partial"
    assert task["job"]["scope"] == "achievements" and task["job"]["app_id"] == APP
    outcome = task["runs"][0]["outcomes"]
    assert outcome["schema"] == "populated:OK" and outcome["schema.http_status"] == "200"
    assert outcome["achievements.http_status"] == "403"
    assert outcome["achievements.content_type"] == "application/json"
    assert outcome["achievements.business_success"] == "false"
    assert outcome["achievements.business_error"] == "PROFILE_NOT_PUBLIC"
    page = (await client.get(BASE + ACH)).json()
    assert page["latest_job"]["id"] == task["job"]["id"]
    assert page["definition_count"] == 2 and page["known_unlocked"] is None
    assert page["state"]["last_success_at"] is None
    assert all(a["unlocked"] is None for a in page["items"])
    assert (await client.get(BASE + "/friends")).json()["latest_job"] is None
    another = await auth.client()
    await auth.login(another)
    assert (await another.get(BASE + "/sync-jobs/" + task["job"]["id"])).status_code == 404


async def expire_schema(auth):
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(
            update(AchievementSchema)
            .where(AchievementSchema.app_id == APP)
            .values(
                last_success_at=utcnow() - timedelta(days=2),
                retry_at=None,
                lease_until=None,
                lease_token=None,
            )
        )


async def test_pipeline_exact_coverage_paging_scope_cooldown_and_no_implicit_fetch(details):
    auth, client, owner = details
    before = (await client.get(BASE + "/sync-status")).json()["latest_job"]["id"]
    assert (await client.get(BASE + ACH)).json()["coverage"] == "unknown"
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return transport(request)

    job = await sync(auth, client, handler=handler)
    assert job["job"]["status"] == "succeeded" and len(calls) == 2
    assert all("GetOwnedGames" not in c for c in calls)
    assert (await client.get(BASE + "/sync-status")).json()["latest_job"]["id"] == before
    page = (await client.get(BASE + ACH + "?limit=1")).json()
    assert page["coverage"] == "complete" and page["completion_percent"] == 50
    assert (
        page["definition_count"] == 2 and page["known_unlocked"] == 1 and page["known_locked"] == 1
    )
    assert page["items"][0]["unlocked_at"] and len(page["items"]) == 1
    other = (
        await client.get(
            BASE + ACH,
            params={
                "after": page["next_after"],
                "snapshot": page["state"]["snapshot_id"],
                "revision": page["schema_state"]["revision"],
            },
        )
    ).json()
    assert other["items"][0]["hidden"] and other["items"][0]["unlocked_at"] is None
    assert (
        await client.post(BASE + ACH + "/sync", headers=await auth.headers(client))
    ).status_code == 429
    assert (await client.get(BASE + ACH + "?after=FIRST")).status_code == 409
    await make_due(auth, owner)
    calls.clear()
    await sync(auth, client, handler=handler)
    assert len(calls) == 1 and "GetPlayerAchievements" in calls[0]
    async with auth.resources.sessions() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(UserAchievement)
                .where(UserAchievement.user_id == owner)
            )
            == 2
        )


@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "unexpected",
        "unknown_state",
        "empty",
        "schema_failure",
        "player_failure",
        "reset",
    ],
)
async def test_coverage_and_independent_resource_results(details, case):
    auth, client, owner = details

    def handler(request):
        if "GetSchema" in request.url.path:
            if case == "schema_failure":
                return httpx.Response(200, json={"game": {}})
            data = schema_payload()
            if case == "empty":
                data["game"]["availableGameStats"]["achievements"] = []
            return httpx.Response(200, json=data)
        data = player_payload(request.url.params["steamid"])
        rows = data["playerstats"]["achievements"]
        if case == "missing":
            rows.pop()
        if case == "unexpected":
            rows.append({"apiname": "NEW", "achieved": 1})
        if case == "unknown_state":
            rows[0].pop("achieved")
            rows[0].pop("unlocktime")
        if case == "empty":
            data["playerstats"]["achievements"] = []
        if case == "player_failure":
            data = {"playerstats": {"success": False}}
        if case == "reset":
            rows[0].update(achieved=0, unlocktime=0)
        return httpx.Response(200, json=data)

    if case == "reset":
        await sync(auth, client)
        await make_due(auth, owner)
    job = await sync(auth, client, handler=handler)
    result = (await client.get(BASE + ACH)).json()
    if case == "empty":
        assert (
            result["coverage"] == "no_achievements"
            and result["completion_percent"] is None
            and result["definition_count"] == 0
        )
    elif case == "reset":
        assert result["completion_percent"] == 0 and result["known_unlocked"] == 0
    else:
        assert result["completion_percent"] is None and job["job"]["status"] == "partial"
        if case == "unexpected":
            assert any(
                i["api_name"] == "NEW" and not i["definition_available"] for i in result["items"]
            )
        if case == "player_failure":
            assert result["known_unlocked"] is None and result["schema_state"]["revision"]
        if case == "schema_failure":
            assert result["known_unlocked"] == 1 and result["schema_state"]["revision"] is None


async def test_schema_revisions_do_not_cascade_player_rows_and_failed_refresh_preserves(details):
    auth, client, owner = details
    await sync(auth, client)
    before = (await client.get(BASE + ACH)).json()
    other = await auth.client()
    await auth.login(other)
    await queue(auth, other)
    await work(auth)
    await expire_schema(auth)

    def changed(request):
        if "GetSchema" in request.url.path:
            data = schema_payload()
            definitions = data["game"]["availableGameStats"]["achievements"]
            definitions.pop()
            definitions.append({"name": "ADDED", "displayName": "Added", "hidden": 0})
            return httpx.Response(200, json=data)
        return transport(request)

    await sync(auth, other, handler=changed)
    result = (await client.get(BASE + ACH)).json()
    assert result["completion_percent"] is None and result["coverage"] == "partial"
    assert any(
        i["api_name"] == "SECRET" and not i["definition_available"] and i["unlocked"] is False
        for i in result["items"]
    )
    async with auth.resources.sessions() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(UserAchievement)
                .where(UserAchievement.user_id == owner)
            )
            == 2
        )
    await expire_schema(auth)
    await make_due(auth, owner)
    await sync(
        auth,
        client,
        handler=lambda r: (
            httpx.Response(200, text="broken") if "GetSchema" in r.url.path else transport(r)
        ),
    )
    failed = (await client.get(BASE + ACH)).json()
    assert (
        failed["schema_state"]["revision"]
        == result["schema_state"]["revision"]
        != before["schema_state"]["revision"]
    )
    assert failed["schema_state"]["stale"] and failed["completion_percent"] is None


async def test_two_users_reuse_schema_but_not_progress_and_clear_keeps_other_owner(details):
    auth, client, owner = details
    await sync(auth, client)
    other = await auth.client()
    other_account = await auth.login(other)
    await queue(auth, other)
    await work(auth)
    calls = []

    def locked(request):
        calls.append(request.url.path)
        if "GetPlayerAchievements" in request.url.path:
            data = player_payload(request.url.params["steamid"])
            for item in data["playerstats"]["achievements"]:
                item.update(achieved=0, unlocktime=0)
            return httpx.Response(200, json=data)
        return transport(request)

    await sync(auth, other, handler=locked)
    assert len(calls) == 1
    assert (await client.get(BASE + ACH)).json()["known_unlocked"] == 1
    assert (await other.get(BASE + ACH)).json()["known_unlocked"] == 0
    await sync(auth, client, "/friends")
    assert (await client.get("/api/v1/me")).json()["steam_data_synchronized"] is True
    assert (
        await client.request(
            "DELETE",
            BASE + "/data",
            headers=await auth.headers(client),
            json={"confirmation": "CLEAR STEAM DATA"},
        )
    ).status_code == 204
    assert (await client.get(BASE + ACH)).status_code == 404
    assert (await client.get(BASE + "/friends")).json()["state"]["status"] == "never"
    assert (await other.get(BASE + ACH)).json()["completion_percent"] == 0
    async with auth.resources.sessions() as db:
        assert await db.get(AchievementSchema, (APP, "english")) is not None
        for table in (UserAchievement, AchievementState, SteamFriend):
            assert (
                await db.scalar(
                    select(func.count()).select_from(table).where(table.user_id == owner)
                )
                == 0
            )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(SyncJob)
                .where(SyncJob.user_id == owner, SyncJob.scope != "base")
            )
            == 0
        )
        assert await db.get(User, UUID(other_account["id"])) is not None


async def test_concurrent_schema_refresh_is_single_flight_without_open_http_transaction(details):
    auth, client, owner = details
    other = await auth.client()
    other_account = await auth.login(other)
    await queue(auth, other)
    await work(auth)
    await client.post(BASE + ACH + "/sync", headers=await auth.headers(client))
    first = await claim_next(auth.resources, auth.config)
    await other.post(BASE + ACH + "/sync", headers=await auth.headers(other))
    second = await claim_next(auth.resources, auth.config)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def blocked(request):
        calls.append(request.url.path)
        if "GetSchema" in request.url.path:
            entered.set()
            await release.wait()
        return transport(request)

    task = asyncio.create_task(
        process_claim(
            auth.resources,
            auth.config,
            SteamClient(auth.config, httpx.MockTransport(blocked)),
            first,
        )
    )
    await asyncio.wait_for(entered.wait(), 3)
    try:
        await asyncio.wait_for(
            process_claim(
                auth.resources,
                auth.config,
                SteamClient(auth.config, httpx.MockTransport(blocked)),
                second,
            ),
            3,
        )
        # Both owners can still GET while first schema HTTP is blocked: user locks released.
        assert (await asyncio.wait_for(client.get(BASE + ACH), 3)).status_code == 200
        assert (await asyncio.wait_for(other.get(BASE + ACH), 3)).status_code == 200
        assert len(calls) == 1
    finally:
        release.set()
        await task
    await make_due(auth, UUID(other_account["id"]))
    await work(auth, blocked)
    assert sum("GetSchema" in c for c in calls) == 1
    assert (await other.get(BASE + ACH)).json()["completion_percent"] == 50


@pytest.mark.parametrize(
    "case", ["401", "403", "malformed", "duplicate", "partial", "empty", "removed", "timeout"]
)
async def test_friends_reconciliation_privacy_and_counts(details, case):
    auth, client, owner = details
    async with auth.resources.sessions() as db:
        before = await db.scalar(select(func.count()).select_from(User))
    await sync(auth, client, "/friends")
    previous = (await client.get(BASE + "/friends?limit=1")).json()
    assert previous["total_count"] == 2 and previous["next_after"], previous
    assert (await client.get(BASE + "/friends?after=" + previous["next_after"])).status_code == 409
    await make_due(auth, owner)

    def handler(request):
        if case in {"401", "403"}:
            return httpx.Response(int(case))
        if case == "timeout":
            raise httpx.ReadTimeout("synthetic")
        if case == "malformed":
            return httpx.Response(200, json={"friendslist": {"friends": [{}]}})
        data = friends_payload()
        if case == "duplicate":
            data["friendslist"]["friends"] *= 2
        if case == "partial":
            data["friendslist"]["has_more"] = True
        if case == "empty":
            data["friendslist"]["friends"] = []
        if case == "removed":
            data["friendslist"]["friends"].pop()
        return httpx.Response(200, json=data)

    await sync(auth, client, "/friends", handler)
    current = (await client.get(BASE + "/friends")).json()
    if case in {"401", "403", "partial"}:
        assert (
            current["items"] == []
            and current["total_count"] is None
            and not current["state"]["data_available"]
        )
    elif case in {"malformed", "duplicate", "timeout"}:
        assert current["total_count"] == 2 and current["state"]["stale"]
        assert current["state"]["last_success_at"] == previous["state"]["last_success_at"]
    else:
        assert current["total_count"] == (0 if case == "empty" else 1)
    async with auth.resources.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(User)) == before
        count = await db.scalar(
            select(func.count()).select_from(SteamFriend).where(SteamFriend.user_id == owner)
        )
        assert count == (0 if case == "empty" else 1 if case == "removed" else 2)


@pytest.mark.parametrize("path", [ACH, "/friends"])
@pytest.mark.parametrize("deleting", [False, True])
async def test_clear_delete_fences_inflight_new_resources(details, path, deleting):
    auth, client, owner = details
    if path == ACH:
        await sync(auth, client)
        await make_due(auth, owner)
    await client.post(BASE + path + "/sync", headers=await auth.headers(client))
    entered, release = asyncio.Event(), asyncio.Event()

    async def blocked(request):
        entered.set()
        await release.wait()
        return transport(request)

    task = asyncio.create_task(work(auth, blocked))
    await asyncio.wait_for(entered.wait(), 3)
    try:
        response = await asyncio.wait_for(
            client.request(
                "DELETE",
                "/api/v1/me" if deleting else BASE + "/data",
                headers=await auth.headers(client),
                json={"confirmation": "DELETE" if deleting else "CLEAR STEAM DATA"},
            ),
            3,
        )
        assert response.status_code == 204
    finally:
        release.set()
        await task
    async with auth.resources.sessions() as db:
        for table in (UserAchievement, AchievementState, SteamFriend):
            assert (
                await db.scalar(
                    select(func.count()).select_from(table).where(table.user_id == owner)
                )
                == 0
            )
        if path == ACH:
            assert await db.get(AchievementSchema, (APP, "english")) is not None


async def test_owner_csrf_eligibility_scopes_and_stale_visibility(details):
    auth, client, owner = details
    anonymous = await auth.client()
    for path in (ACH, "/friends"):
        assert (await anonymous.get(BASE + path)).status_code == 401
        assert (await client.post(BASE + path + "/sync")).status_code == 403
    assert (
        await client.post(
            BASE + f"/games/{APP + 99}/achievements/sync", headers=await auth.headers(client)
        )
    ).status_code == 404
    ach = await client.post(BASE + ACH + "/sync", headers=await auth.headers(client))
    duplicate = await client.post(BASE + ACH + "/sync", headers=await auth.headers(client))
    assert duplicate.status_code == 200 and duplicate.json()["job"]["id"] == ach.json()["job"]["id"]
    friend = await client.post(BASE + "/friends/sync", headers=await auth.headers(client))
    next_game = await client.post(
        BASE + f"/games/{APP + 1}/achievements/sync", headers=await auth.headers(client)
    )
    assert len({r.json()["job"]["id"] for r in (ach, friend, next_game)}) == 3
    other = await auth.client()
    await auth.login(other)
    assert (await other.get(BASE + ACH)).status_code == 404
    assert (await other.get(BASE + "/sync-jobs/" + friend.json()["job"]["id"])).status_code == 404
    for _ in range(3):
        await work(auth, transport)
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(
            update(SyncState)
            .where(SyncState.user_id == owner, SyncState.resource == "friends")
            .values(last_success_at=utcnow() - timedelta(minutes=16))
        )
        await db.execute(
            update(AchievementState)
            .where(AchievementState.user_id == owner)
            .values(last_success_at=utcnow() - timedelta(minutes=16))
        )
    assert (await client.get(BASE + "/friends")).json()["total_count"] is None
    assert (await client.get(BASE + ACH)).json()["coverage"] == "stale"
    assert (await client.get(BASE + ACH)).json()["completion_percent"] is None


@pytest.mark.parametrize("path", [ACH, "/friends"])
async def test_new_scopes_restart_expired_lease_rejects_old_result(details, path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    from steamscope_social.modules.steam.client import Snapshot
    from steamscope_social.modules.steam.jobs import save_resource
    from tests.steam_fixtures import KEY

    auth, client, owner = details
    response = await client.post(BASE + path + "/sync", headers=await auth.headers(client))
    job_id = response.json()["job"]["id"]
    env = dict(os.environ, SOCIAL_STEAM_API_KEY=KEY)
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
            assert job.status == "running"
            job.lease_until = utcnow() - timedelta(seconds=1)
            await db.execute(
                update(AchievementSchema)
                .where(AchievementSchema.app_id == APP)
                .values(lease_until=utcnow() - timedelta(seconds=1))
            )
        result = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, str(script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, "Synthetic worker restart failed"
        saved = (await client.get(BASE + "/sync-jobs/" + job_id)).json()
        assert saved["job"]["status"] == "succeeded" and saved["job"]["attempts"] == 2
        assert saved["runs"][0]["status"] == "lease_expired"
        await make_due(auth, owner)
        await client.post(BASE + path + "/sync", headers=await auth.headers(client))
        old = await claim_next(auth.resources, auth.config)
        async with auth.resources.sessions() as db, db.begin():
            await db.execute(
                update(SyncJob)
                .where(SyncJob.id == old.job_id)
                .values(lease_until=utcnow() - timedelta(seconds=1))
            )
        await work(auth, transport)
        assert not await save_resource(
            auth.resources,
            old,
            "achievements" if path == ACH else "friends",
            Snapshot("empty", "OK"),
        )
    finally:
        if child.poll() is None:
            child.kill()
            await asyncio.to_thread(child.wait, timeout=5)


async def test_schema_calls_consume_shared_budget_and_retry_is_bounded(details):
    auth, client, owner = details
    async with auth.resources.sessions() as db:
        before = (await db.get(RequestBudget, ("user", str(owner)))).used
    calls = []

    def failed(request):
        calls.append(request.url.path)
        return (
            httpx.Response(503)
            if "GetPlayerAchievements" in request.url.path
            else transport(request)
        )

    job = await sync(auth, client, handler=failed)
    assert job["job"]["status"] == "retry"
    for _ in range(2):
        await make_due(auth, owner)
        await work(auth, failed)
    saved = (await client.get(BASE + "/sync-jobs/" + job["job"]["id"])).json()
    assert saved["job"]["status"] == "partial" and saved["job"]["attempts"] == 3
    assert sum("GetSchema" in c for c in calls) == 1 and len(calls) == 4
    async with auth.resources.sessions() as db:
        assert (await db.get(RequestBudget, ("user", str(owner)))).used - before == 4
    auth.config.steam_user_requests_per_hour = 3
    calls.clear()
    limited = await sync(auth, client, "/friends", failed)
    assert limited["job"]["status"] == "retry" and calls == []


async def test_lost_library_eligibility_hides_progress_and_prevents_late_write(details):
    auth, client, owner = details
    await sync(auth, client)
    await make_due(auth, owner)
    await client.post(BASE + ACH + "/sync", headers=await auth.headers(client))
    entered, release = asyncio.Event(), asyncio.Event()

    async def blocked(request):
        entered.set()
        await release.wait()
        return transport(request)

    task = asyncio.create_task(work(auth, blocked))
    await asyncio.wait_for(entered.wait(), 3)
    try:
        async with auth.resources.sessions() as db, db.begin():
            await db.execute(
                update(SyncState)
                .where(SyncState.user_id == owner, SyncState.resource == "library")
                .values(exposed=False, status="unknown")
            )
        assert (await client.get(BASE + ACH)).status_code == 404
        assert (
            await client.post(BASE + ACH + "/sync", headers=await auth.headers(client))
        ).status_code == 404
    finally:
        release.set()
        await task
    async with auth.resources.sessions() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(UserAchievement)
                .where(UserAchievement.user_id == owner)
            )
            == 2
        )


@pytest.mark.parametrize("deleting", [False, True])
async def test_clear_or_delete_during_first_shared_schema_response(details, deleting):
    auth, client, owner = details
    await client.post(BASE + ACH + "/sync", headers=await auth.headers(client))
    entered, release = asyncio.Event(), asyncio.Event()

    async def blocked(request):
        assert "GetSchemaForGame" in request.url.path
        entered.set()
        await release.wait()
        return transport(request)

    task = asyncio.create_task(work(auth, blocked))
    await asyncio.wait_for(entered.wait(), 3)
    try:
        response = await client.request(
            "DELETE",
            "/api/v1/me" if deleting else BASE + "/data",
            headers=await auth.headers(client),
            json={"confirmation": "DELETE" if deleting else "CLEAR STEAM DATA"},
        )
        assert response.status_code == 204
    finally:
        release.set()
        await task
    async with auth.resources.sessions() as db:
        schema = await db.get(AchievementSchema, (APP, "english"))
        assert schema.last_success_at is None and schema.lease_token is None
        for table in (UserAchievement, AchievementState, SteamFriend):
            assert (
                await db.scalar(
                    select(func.count()).select_from(table).where(table.user_id == owner)
                )
                == 0
            )
