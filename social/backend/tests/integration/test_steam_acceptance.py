"""Cross-resource acceptance on isolated synthetic accounts, never the real owner."""

import asyncio
from uuid import UUID

import httpx
import pytest
from sqlalchemy import func, select

from steamscope_social.modules.auth.models import SteamAccount, UserSession
from steamscope_social.modules.auth.security import session_cookie
from steamscope_social.modules.privacy.models import PrivacySettings
from steamscope_social.modules.steam.models import (
    AchievementSchema,
    AchievementState,
    Game,
    RecentGame,
    SteamFriend,
    SyncJob,
    SyncState,
    UserAchievement,
    UserGame,
)
from steamscope_social.modules.users.models import User
from tests.integration.test_steam_details import ACH, BASE, sync
from tests.integration.test_steam_details import details as details
from tests.integration.test_steam_sync import make_due, queue, work
from tests.integration.test_steam_sync import steam as steam
from tests.steam_details_fixtures import player_payload, transport
from tests.steam_fixtures import APP

pytestmark = pytest.mark.integration


async def saved_player(auth, owner):
    async with auth.resources.sessions() as db:
        rows = (
            await db.execute(
                select(
                    UserAchievement.api_name,
                    UserAchievement.unlocked,
                    UserAchievement.unlocked_at,
                    UserAchievement.observed_at,
                )
                .where(UserAchievement.user_id == owner, UserAchievement.app_id == APP)
                .order_by(UserAchievement.api_name)
            )
        ).all()
        state = await db.get(AchievementState, (owner, APP))
        return rows, state.last_success_at, state.snapshot_id, state.schema_revision


@pytest.mark.parametrize("case", ["missing", "unexpected", "unknown_state", "malformed"])
async def test_incomplete_player_cannot_replace_accepted_snapshot(details, case):
    auth, client, owner = details
    await sync(auth, client)
    before = await saved_player(auth, owner)
    await make_due(auth, owner)

    def incomplete(request):
        if "GetPlayerAchievements" not in request.url.path:
            return transport(request)
        data = player_payload(request.url.params["steamid"])
        rows = data["playerstats"]["achievements"]
        if case == "missing":
            rows.pop()
        elif case == "unexpected":
            rows.append({"apiname": "UNCONFIRMED", "achieved": 1})
        elif case == "unknown_state":
            rows[0].pop("achieved")
            rows[0].pop("unlocktime")
        else:
            rows[0]["achieved"] = "invalid"
        return httpx.Response(200, json=data)

    result = await sync(auth, client, handler=incomplete)
    assert result["job"]["status"] == "partial"
    assert await saved_player(auth, owner) == before
    page = (await client.get(BASE + ACH)).json()
    assert page["completion_percent"] is None
    assert page["state"]["last_success_at"] is not None
    if case != "malformed":
        assert not page["state"]["data_available"] and page["known_unlocked"] is None
    await make_due(auth, owner)
    await sync(auth, client)
    assert (await client.get(BASE + ACH)).json()["coverage"] == "complete"
    assert len((await saved_player(auth, owner))[0]) == 2


@pytest.mark.parametrize("resource", ["library", "achievements", "friends"])
async def test_readable_restricted_readable_cross_resource_transition(details, resource):
    auth, client, owner = details
    await sync(auth, client)
    await sync(auth, client, "/friends")
    route = {"library": "/games", "achievements": ACH, "friends": "/friends"}[resource]
    table = {"library": UserGame, "achievements": UserAchievement, "friends": SteamFriend}[resource]
    before = (await client.get(BASE + route)).json()
    async with auth.resources.sessions() as db:
        count = await db.scalar(
            select(func.count()).select_from(table).where(table.user_id == owner)
        )
    await make_due(auth, owner)

    def restricted(request):
        if resource == "library" and "GetOwnedGames" in request.url.path:
            return httpx.Response(200, json={"response": {}})
        if resource == "achievements" and "GetPlayerAchievements" in request.url.path:
            return httpx.Response(
                403, json={"playerstats": {"success": False, "error": "Profile is not public"}}
            )
        if resource == "friends" and "GetFriendList" in request.url.path:
            return httpx.Response(401)
        return transport(request)

    if resource == "library":
        job = await queue(auth, client)
        await work(auth, restricted)
    else:
        task = await sync(auth, client, route, restricted)
        job = task["job"]["id"]
    denied = (await client.get(BASE + route)).json()
    assert not denied["state"]["data_available"]
    assert denied["state"]["last_success_at"] == before["state"]["last_success_at"]
    if resource == "achievements":
        assert denied["definition_count"] == 2
        assert denied["completion_percent"] is None and denied["known_locked"] is None
        assert all(a["unlocked"] is None for a in denied["items"])
    else:
        assert denied["items"] == [] and denied["next_after"] is None
        assert denied["total_minutes" if resource == "library" else "total_count"] is None
    async with auth.resources.sessions() as db:
        assert (
            await db.scalar(select(func.count()).select_from(table).where(table.user_id == owner))
            == count
        )
    old = (await client.get(BASE + "/sync-jobs/" + job)).json()
    assert old["job"]["status"] in {"partial", "failed"}
    await make_due(auth, owner)
    if resource == "library":
        await queue(auth, client)
        await work(auth, transport)
    else:
        await sync(auth, client, route)
    current = (await client.get(BASE + route)).json()
    assert current["state"]["data_available"]
    assert (await client.get(BASE + "/sync-jobs/" + job)).json()["runs"] == old["runs"]
    async with auth.resources.sessions() as db:
        assert (
            await db.scalar(select(func.count()).select_from(table).where(table.user_id == owner))
            == count
        )


@pytest.mark.parametrize("deleting", [False, True])
async def test_all_resource_clear_delete_race_and_reregistration(details, deleting):
    auth, client, owner = details
    await client.patch(
        "/api/v1/me", headers=await auth.headers(client), json={"display_name": "Kept local name"}
    )
    await sync(auth, client)
    await sync(auth, client, "/friends")
    other = await auth.client()
    other_account = await auth.login(other)
    other_id = UUID(other_account["id"])
    await queue(auth, other)
    await work(auth, transport)
    await sync(auth, other)
    await sync(auth, other, "/friends")
    async with auth.resources.sessions() as db:
        link = await db.scalar(select(SteamAccount).where(SteamAccount.user_id == owner))
        identity, generation = link.steam_id, link.import_generation
        assert link.persona_name
        for table in (
            UserGame,
            RecentGame,
            UserAchievement,
            AchievementState,
            SteamFriend,
            SyncState,
        ):
            assert await db.scalar(
                select(func.count()).select_from(table).where(table.user_id == owner)
            )
    copied = client.cookies[session_cookie(auth.config)]
    await make_due(auth, owner)
    await client.post(BASE + ACH + "/sync", headers=await auth.headers(client))
    entered, release = asyncio.Event(), asyncio.Event()

    async def blocked(request):
        entered.set()
        await release.wait()
        return transport(request)

    pending = asyncio.create_task(work(auth, blocked))
    await asyncio.wait_for(entered.wait(), 3)
    try:
        # Other scopes queue while HTTP is outside the transaction; erase must coordinate them.
        await queue(auth, client)
        await client.post(BASE + "/friends/sync", headers=await auth.headers(client))
        response = await client.request(
            "DELETE",
            "/api/v1/me" if deleting else BASE + "/data",
            headers=await auth.headers(client),
            json={"confirmation": "DELETE" if deleting else "CLEAR STEAM DATA"},
        )
        assert response.status_code == 204
    finally:
        release.set()
        await pending
    async with auth.resources.sessions() as db:
        for table in (
            UserGame,
            RecentGame,
            UserAchievement,
            AchievementState,
            SteamFriend,
            SyncState,
        ):
            assert (
                await db.scalar(
                    select(func.count()).select_from(table).where(table.user_id == owner)
                )
                == 0
            )
            assert await db.scalar(
                select(func.count()).select_from(table).where(table.user_id == other_id)
            )
        assert await db.get(Game, APP) and await db.get(AchievementSchema, (APP, "english"))
        active = (
            select(func.count())
            .select_from(SyncJob)
            .where(SyncJob.user_id == owner, SyncJob.status.in_(("queued", "running", "retry")))
        )
        assert await db.scalar(active) == 0
        if deleting:
            assert await db.get(User, owner) is None
            for table in (SteamAccount, UserSession, PrivacySettings, SyncJob):
                assert (
                    await db.scalar(
                        select(func.count()).select_from(table).where(table.user_id == owner)
                    )
                    == 0
                )
        else:
            link = await db.scalar(select(SteamAccount).where(SteamAccount.user_id == owner))
            assert (
                link.steam_id == identity
                and link.verified_at
                and link.import_generation == generation + 1
            )
            assert link.persona_name is None and link.avatar_url is None
            assert (await db.get(User, owner)).display_name == "Kept local name"
            assert await db.get(PrivacySettings, owner)
    if deleting:
        stale = await auth.client()
        stale.cookies.set(session_cookie(auth.config), copied)
        for path in ("/api/v1/me", BASE + "/games", BASE + ACH, BASE + "/friends"):
            assert (await stale.get(path)).status_code == 401
        new = await auth.login(client, identity)
        assert UUID(new["id"]) != owner and new["display_name"] == "New player"
    for path in ("/profile", "/games", "/recent-games", "/friends"):
        assert (await client.get(BASE + path)).json()["state"]["status"] == "never"
    assert (await client.get(BASE + ACH)).status_code == 404
    # A new explicit base sync, not GET or re-registration, restores eligibility.
    if not deleting:
        await make_due(auth, owner)
    await queue(auth, client)
    await work(auth, transport)
    assert (await client.get(BASE + "/games")).json()["returned_game_count"] == 27
    assert (await other.get(BASE + ACH)).json()["completion_percent"] == 50
