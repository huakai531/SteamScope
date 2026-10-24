"""Five synthetic accounts; real isolated PostgreSQL/Redis, no Steam network calls."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select, update

from steamscope_social.core.database import utcnow
from steamscope_social.modules.auth.models import SteamAccount
from steamscope_social.modules.privacy.models import PrivacySettings
from steamscope_social.modules.steam.models import (
    AchievementDefinition,
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

pytestmark = pytest.mark.integration
APP = 77840001


@pytest.fixture
async def players(auth):
    clients, accounts = {}, {}
    for name in "ABCDE":
        clients[name] = await auth.client()
        accounts[name] = await auth.login(clients[name])
    ids = {n: UUID(a["id"]) for n, a in accounts.items()}
    now = utcnow()
    async with auth.resources.sessions() as db, db.begin():
        for i, title in enumerate(["Alpha", "Beta {x,y}%_", "Gamma", "Delta"]):
            await db.merge(Game(app_id=APP + i, name=title))
        await db.flush()
        for n, owner in ids.items():
            await db.execute(
                update(PrivacySettings)
                .where(PrivacySettings.user_id == owner)
                .values(
                    profile="public",
                    library="private" if n == "C" else "public",
                    playtime="public",
                    achievements="private" if n == "C" else "public",
                )
            )
            for resource in ["profile", "library", "recent"]:
                db.add(
                    SyncState(
                        user_id=owner,
                        resource=resource,
                        status="empty" if n == "D" else "populated",
                        code="OK",
                        exposed=True,
                        snapshot_id=uuid4(),
                        last_success_at=now - timedelta(days=2) if n == "E" else now,
                    )
                )
            apps = [] if n == "D" else ([0, 1, 3] if n == "B" else [0, 1, 2])
            for i in apps:
                db.add(
                    UserGame(
                        user_id=owner,
                        app_id=APP + i,
                        total_minutes=[60, None, 0, 120][i],
                        recent_minutes=[0, None, 0, 5][i],
                        last_played_at=now if i == 0 else None,
                        observed_at=now,
                    )
                )
            if apps:
                db.add(
                    RecentGame(
                        user_id=owner,
                        app_id=APP,
                        total_minutes=60,
                        recent_minutes=0,
                        observed_at=now,
                    )
                )
        for i in [0, 1]:
            db.add(
                AchievementSchema(
                    app_id=APP + i,
                    language="english",
                    status="populated",
                    code="OK",
                    revision="r1",
                    last_success_at=now,
                )
            )
        await db.flush()
        for i in [0, 1]:
            for key in ["ONE", "TWO"]:
                db.add(
                    AchievementDefinition(
                        app_id=APP + i,
                        language="english",
                        api_name=key,
                        display_name=key,
                        hidden=False,
                    )
                )
            for n in "ABCE":
                db.add(
                    AchievementState(
                        user_id=ids[n],
                        app_id=APP + i,
                        status="partial" if n == "B" and i == 1 else "populated",
                        code="OK",
                        exposed=True,
                        snapshot_id=uuid4(),
                        schema_revision="r1",
                        last_success_at=now - timedelta(days=2) if n == "E" else now,
                    )
                )
                for key in ["ONE"] if n == "B" and i == 1 else ["ONE", "TWO"]:
                    db.add(
                        UserAchievement(
                            user_id=ids[n],
                            app_id=APP + i,
                            api_name=key,
                            unlocked=key == "ONE",
                            unlocked_at=now if key == "ONE" else None,
                            observed_at=now,
                        )
                    )
    try:
        yield auth, clients, accounts, ids
    finally:
        # Only owned synthetic associations and the reserved fixture app range.
        async with auth.resources.sessions() as db, db.begin():
            for model in [UserAchievement, AchievementState, UserGame, RecentGame]:
                await db.execute(delete(model).where(model.user_id.in_(ids.values())))
            await db.execute(
                delete(AchievementSchema).where(AchievementSchema.app_id.between(APP, APP + 3))
            )
            await db.execute(delete(Game).where(Game.app_id.between(APP, APP + 3)))
            await db.execute(delete(User).where(User.id.in_(ids.values())))


def path(accounts, name="A", suffix=""):
    return "/api/v1/users/" + accounts[name]["handle"] + suffix


async def change(auth, owner, model=PrivacySettings, **values):
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(update(model).where(model.user_id == owner).values(**values))


async def test_anonymous_and_unverified_profiles_fail_closed(players):
    auth, clients, accounts, ids = players
    anonymous = await auth.client()
    for suffix in ["", "/games", f"/games/{APP}", f"/games/{APP}/achievements", "/comparison"]:
        assert (await anonymous.get(path(accounts, suffix=suffix))).status_code == 401
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(delete(SteamAccount).where(SteamAccount.user_id == ids["A"]))
    assert (await clients["A"].get(path(accounts))).status_code == 404
    assert (await clients["B"].get(path(accounts))).status_code == 404


@pytest.mark.parametrize("visibility", ["public", "private", "connections"])
@pytest.mark.parametrize("resource", ["profile", "library", "playtime", "achievements"])
async def test_resource_visibility_owner_stranger_matrix(players, visibility, resource):
    auth, clients, accounts, ids = players
    await change(auth, ids["A"], **{resource: visibility})
    for viewer in ["A", "B"]:
        allowed = viewer == "A" or visibility == "public"
        response = await clients[viewer].get(path(accounts))
        if resource == "profile" and not allowed:
            absent = await clients[viewer].get("/api/v1/users/nonexistent_fixture")
            assert response.status_code == absent.status_code == 404
            assert response.json()["error"] == absent.json()["error"]
            for suffix in ["/games", f"/games/{APP}", f"/games/{APP}/achievements", "/comparison"]:
                assert (await clients[viewer].get(path(accounts, suffix=suffix))).status_code == 404
            continue
        assert response.status_code == 200
        profile = response.json()
        library = (await clients[viewer].get(path(accounts, suffix="/games"))).json()
        compare = (await clients[viewer].get(path(accounts, suffix="/comparison"))).json()
        assert "steam_id" not in response.text and str(ids["A"]) not in response.text
        if viewer != "A":
            assert profile["locale"] is profile["timezone"] is None
        if resource == "library" and not allowed:
            assert (
                library["items"] == []
                and library["total_count"] is None
                and library["next_cursor"] is None
            )
            assert (
                profile["game_count"]
                is profile["total_minutes"]
                is profile["synchronized_achievement_games"]
                is None
            )
            assert profile["most_played"] == profile["recent_games"] == []
            assert compare["items"] == [] and compare["mutual_count"] is None
            assert compare["left_total_minutes"] is compare["right_total_minutes"] is None
            assert (
                await clients[viewer].get(path(accounts, suffix=f"/games/{APP}"))
            ).status_code == 404
        elif resource == "playtime" and not allowed:
            assert (
                profile["total_minutes"] is None
                and profile["most_played"] == profile["recent_games"] == []
            )
            assert all(
                g["total_minutes"] is g["recent_minutes"] is g["last_played_at"] is None
                for g in library["items"]
            )
            assert all(
                g["difference_minutes"] is g["right_minutes"] is g["left_recent_minutes"] is None
                for g in compare["items"]
            )
            for query in ["sort=total", "sort=recent", "sort=last_played", "recent=true"]:
                assert (
                    await clients[viewer].get(path(accounts, suffix="/games?" + query))
                ).status_code == 422
        elif resource == "achievements" and not allowed:
            assert profile["synchronized_achievement_games"] is None
            progress = (
                await clients[viewer].get(path(accounts, suffix=f"/games/{APP}/achievements"))
            ).json()
            assert progress["items"] == []
            assert (
                progress["progress"]["definition_count"]
                is progress["progress"]["known_unlocked"]
                is progress["progress"]["completion_percent"]
                is None
            )
            assert compare["comparable_achievement_games"] is None
            assert all(
                g["right_completion"] is g["left_completion"] is None for g in compare["items"]
            )
            assert (
                await clients[viewer].get(path(accounts, suffix="/games?achievements=true"))
            ).status_code == 422
        else:
            assert library["total_count"] == 3
    # Imported friend edges confer no authorization.
    if visibility == "connections":
        async with auth.resources.sessions() as db, db.begin():
            steamid = await db.scalar(
                select(SteamAccount.steam_id).where(SteamAccount.user_id == ids["B"])
            )
            db.add(SteamFriend(user_id=ids["A"], friend_steam_id64=steamid, observed_at=utcnow()))
        again = await clients["B"].get(path(accounts))
        assert again.status_code == (404 if resource == "profile" else 200)
        if resource != "profile":
            assert again.json() == response.json()


@pytest.mark.parametrize("source", ["stale", "restricted", "never", "failed"])
async def test_source_matrix_and_owner_stale_policy(players, source):
    auth, clients, accounts, ids = players
    async with auth.resources.sessions() as db, db.begin():
        for model in [SyncState, AchievementState]:
            stmt = update(model).where(model.user_id == ids["A"])
            if source == "never":
                await db.execute(delete(model).where(model.user_id == ids["A"]))
            else:
                values = (
                    dict(status="unavailable", exposed=False)
                    if source == "restricted"
                    else dict(last_success_at=utcnow() - timedelta(days=2))
                )
                if source == "failed":
                    values = dict(status="failed", exposed=True)
                await db.execute(stmt.values(**values))
    for viewer in ["A", "B"]:
        profile = (await clients[viewer].get(path(accounts))).json()
        games = (await clients[viewer].get(path(accounts, suffix="/games"))).json()
        visible = viewer == "A" and source in {"stale", "failed"}
        assert profile["library_state"]["data_available"] == visible
        assert (games["total_count"] == 3) == visible
        assert profile["recent_games"] == []
        if visible:
            assert games["items"][0]["achievements"]["completion_percent"] is None
        else:
            assert games["items"] == [] and profile["game_count"] is None
            assert (await clients[viewer].get(path(accounts, suffix="/comparison"))).json()[
                "mutual_count"
            ] is None


async def test_comparison_overlap_partial_unknown_zero_and_empty(players):
    _, clients, accounts, _ = players
    data = (await clients["A"].get(path(accounts, "B", "/comparison"))).json()
    assert data["mutual_count"] == 2 and [g["app_id"] for g in data["items"]] == [APP, APP + 1]
    first, second = data["items"]
    assert (
        first["left_minutes"] == first["right_minutes"] == 60 and first["difference_minutes"] == 0
    )
    assert first["left_recent_minutes"] == first["right_recent_minutes"] == 0
    assert first["left_completion"] == first["right_completion"] == 50
    assert second["left_minutes"] is second["right_minutes"] is second["difference_minutes"] is None
    assert second["left_completion"] is second["right_completion"] is None
    assert second["right_achievements"]["coverage"] == "partial"
    assert data["left_total_minutes"] is data["right_total_minutes"] is None
    assert data["comparable_achievement_games"] == 1
    empty = (await clients["A"].get(path(accounts, "D", "/comparison"))).json()
    assert empty["status"] == "available" and empty["items"] == [] and empty["mutual_count"] == 0
    assert empty["left_total_minutes"] == empty["right_total_minutes"] == 0
    assert (await clients["A"].get(path(accounts, "C", "/comparison"))).json()[
        "mutual_count"
    ] is None
    assert (await clients["A"].get(path(accounts, "E", "/comparison"))).json()[
        "mutual_count"
    ] is None


async def test_pagination_filters_literal_search_bounds_and_viewer_binding(players):
    auth, clients, accounts, ids = players
    for suffix in ["/games", "/comparison", f"/games/{APP}/achievements"]:
        first = (await clients["A"].get(path(accounts, "B", suffix), params={"limit": 1})).json()
        assert first["next_cursor"]
        second = (
            await clients["A"].get(
                path(accounts, "B", suffix), params={"limit": 1, "cursor": first["next_cursor"]}
            )
        ).json()
        key = "api_name" if suffix.endswith("achievements") else "app_id"
        assert first["items"][0][key] != second["items"][0][key]
        assert (
            await clients["C"].get(
                path(accounts, "B", suffix), params={"cursor": first["next_cursor"]}
            )
        ).status_code == 409
    url = path(accounts, suffix="/games")
    assert (await clients["A"].get(url, params={"q": "{x,y}%_"})).json()["total_count"] == 1
    assert (await clients["A"].get(url, params={"q": "*"})).json()["total_count"] == 0
    for params in [
        {"sort": "injected"},
        {"limit": 0},
        {"limit": 101},
        {"q": "x" * 81},
        {"cursor": "invalid!"},
    ]:
        assert (await clients["A"].get(url, params=params)).status_code == 422
    for sort, ordered in [
        ("name", [APP, APP + 1, APP + 2]),
        ("total", [APP, APP + 2, APP + 1]),
        ("recent", [APP, APP + 2, APP + 1]),
        ("last_played", [APP, APP + 1, APP + 2]),
    ]:
        seen, cursor = [], None
        while True:
            params = {"sort": sort, "limit": 1}
            if cursor:
                params["cursor"] = cursor
            page = (await clients["A"].get(url, params=params)).json()
            seen.extend(g["app_id"] for g in page["items"])
            cursor = page["next_cursor"]
            if not cursor:
                break
        assert seen == ordered
    assert (await clients["A"].get(url, params={"recent": True})).json()["total_count"] == 0
    assert (await clients["A"].get(url, params={"achievements": True})).json()["total_count"] == 2
    token = (await clients["B"].get(url, params={"limit": 1})).json()["next_cursor"]
    await change(auth, ids["A"], playtime="private")
    assert (await clients["B"].get(url, params={"cursor": token})).status_code == 409


async def test_privacy_clear_delete_handle_reuse_and_no_read_jobs(players):
    auth, clients, accounts, ids = players
    async with auth.resources.sessions() as db:
        before = await db.scalar(select(func.count()).select_from(SyncJob))
    url = path(accounts, "B", "/comparison")
    assert (await clients["A"].get(url)).json()["mutual_count"] == 2
    await change(auth, ids["B"], library="private")
    assert (await clients["A"].get(url)).json()["mutual_count"] is None
    await change(auth, ids["B"], library="public")
    result = await clients["B"].request(
        "DELETE",
        "/api/v1/me/steam/data",
        headers=await auth.headers(clients["B"]),
        json={"confirmation": "CLEAR STEAM DATA"},
    )
    assert result.status_code == 204
    assert (await clients["A"].get(url)).json()["mutual_count"] is None
    old = accounts["B"]["handle"]
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(
            update(User).where(User.id == ids["B"]).values(handle="p4_" + uuid4().hex[:15])
        )
    assert (await clients["A"].get(url)).status_code == 404
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(update(User).where(User.id == ids["C"]).values(handle=old))
    assert (await clients["A"].get(url)).json()["mutual_count"] is None
    await auth.login(clients["C"], auth.identities[2])
    result = await clients["C"].request(
        "DELETE",
        "/api/v1/me",
        headers=await auth.headers(clients["C"]),
        json={"confirmation": "DELETE"},
    )
    assert result.status_code == 204
    assert (await clients["A"].get(url)).status_code == 404
    async with auth.resources.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(SyncJob)) == before


async def test_schema_incompatibility_and_zero_definitions_no_fabricated_completion(players):
    auth, clients, accounts, _ = players
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(
            update(AchievementSchema).where(AchievementSchema.app_id == APP).values(revision="r2")
        )
    data = (await clients["A"].get(path(accounts, suffix=f"/games/{APP}/achievements"))).json()
    assert (
        data["progress"]["coverage"] == "partial" and data["progress"]["completion_percent"] is None
    )
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(
            update(AchievementSchema)
            .where(AchievementSchema.app_id == APP)
            .values(revision="r1", status="empty")
        )
        await db.execute(delete(AchievementDefinition).where(AchievementDefinition.app_id == APP))
        await db.execute(delete(UserAchievement).where(UserAchievement.app_id == APP))
    data = (await clients["A"].get(path(accounts, suffix=f"/games/{APP}/achievements"))).json()
    assert (
        data["progress"]["coverage"] == "no_achievements"
        and data["progress"]["completion_percent"] is None
    )


@pytest.mark.parametrize("source", ["stale", "restricted", "never", "failed"])
async def test_independent_achievement_source_never_leaks_progress_or_hides_visible_library(
    players, source
):
    auth, clients, accounts, ids = players
    async with auth.resources.sessions() as db, db.begin():
        statement = update(AchievementState).where(AchievementState.user_id == ids["A"])
        if source == "never":
            await db.execute(delete(AchievementState).where(AchievementState.user_id == ids["A"]))
        elif source == "restricted":
            await db.execute(statement.values(status="unavailable", exposed=False))
        elif source == "failed":
            await db.execute(statement.values(status="failed", exposed=True))
        else:
            await db.execute(statement.values(last_success_at=utcnow() - timedelta(days=2)))
    for viewer in ["A", "B"]:
        library = (await clients[viewer].get(path(accounts, suffix="/games"))).json()
        assert library["total_count"] == 3
        result = (
            await clients[viewer].get(path(accounts, suffix=f"/games/{APP}/achievements"))
        ).json()
        visible = viewer == "A" and source in {"stale", "failed"}
        assert result["progress"]["state"]["data_available"] == visible
        assert result["progress"]["completion_percent"] is None
        if visible:
            assert result["progress"]["known_unlocked"] == 1 and len(result["items"]) == 2
        else:
            assert (
                result["items"] == []
                and result["progress"]["known_unlocked"]
                is result["progress"]["definition_count"]
                is None
            )
        c = (await clients[viewer].get(path(accounts, suffix="/comparison"))).json()
        assert c["mutual_count"] in {2, 3}
        assert c["comparable_achievement_games"] == 0
        assert all(i["left_completion"] is i["right_completion"] is None for i in c["items"])


async def test_achievement_in_progress_is_owner_and_app_scoped(players):
    auth, clients, accounts, ids = players
    async with auth.resources.sessions() as db, db.begin():
        link_id = await db.scalar(select(SteamAccount.id).where(SteamAccount.user_id == ids["A"]))
        db.add(
            SyncJob(
                user_id=ids["A"],
                link_id=link_id,
                generation=0,
                scope="achievements",
                app_id=APP,
                status="queued",
            )
        )
    for viewer in ["A", "B"]:
        games = (await clients[viewer].get(path(accounts, suffix="/games"))).json()["items"]
        for game in games:
            assert game["achievements"]["state"]["in_progress"] == (
                viewer == "A" and game["app_id"] == APP
            )
        assert not (await clients[viewer].get(path(accounts))).json()["library_state"][
            "in_progress"
        ]
