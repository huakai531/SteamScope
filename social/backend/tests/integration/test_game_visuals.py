import httpx
import pytest
from sqlalchemy import select, update

from steamscope_social.modules.steam.models import Game
from tests.integration.test_players import APP, players  # noqa: F401
from tests.integration.test_steam_sync import make_due, queue, steam, work  # noqa: F401
from tests.steam_fixtures import transport

pytestmark = pytest.mark.integration


async def test_visuals_share_source_and_follow_library_authorization(players):  # noqa: F811
    auth, clients, accounts, ids = players
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(update(Game).where(Game.app_id == APP).values(icon_hash="a" * 40))
    a = (await clients["A"].get("/api/v1/users/" + accounts["A"]["handle"] + "/games")).json()
    b = (await clients["A"].get("/api/v1/users/" + accounts["B"]["handle"] + "/games")).json()
    av = next(g["visual"] for g in a["items"] if g["app_id"] == APP)
    bv = next(g["visual"] for g in b["items"] if g["app_id"] == APP)
    assert av == bv and av["icon_url"].endswith("a" * 40 + ".jpg")
    assert av["card_url"].endswith(f"/{APP}/library_hero.jpg")
    assert av["thumbnail_url"].endswith(f"/{APP}/header.jpg")
    hidden = await clients["A"].get("/api/v1/users/" + accounts["C"]["handle"] + "/games")
    assert hidden.json()["items"] == []
    assert "media.steampowered.com" not in hidden.text
    assert "steamstatic.com" not in hidden.text
    comparison = await clients["A"].get("/api/v1/users/" + accounts["C"]["handle"] + "/comparison")
    assert "media.steampowered.com" not in comparison.text
    assert "steamstatic.com" not in comparison.text


async def test_sync_updates_visuals_and_preserves_on_missing_or_failed_source(steam):  # noqa: F811
    auth, client, user = steam

    def handler(icon, failure=False):
        def respond(request):
            if "GetOwnedGames" in request.url.path:
                if failure:
                    return httpx.Response(503)
                return httpx.Response(
                    200,
                    json={
                        "response": {
                            "game_count": 1,
                            "games": [
                                {
                                    "appid": 77860001,
                                    "name": "Synthetic artwork game",
                                    "img_icon_url": icon,
                                    "playtime_forever": 456,
                                }
                            ],
                        }
                    },
                )
            return transport(request)

        return respond

    for icon, failure in [
        ("a" * 40, False),
        (None, False),
        ({}, False),
        ("b" * 40, False),
        (None, True),
    ]:
        await make_due(auth, user)
        await queue(auth, client)
        await work(auth, handler(icon, failure))
        async with auth.resources.sessions() as db:
            game = await db.get(Game, 77860001)
            assert game.icon_hash == ("b" * 40 if failure or icon == "b" * 40 else "a" * 40)
            assert len(list(await db.scalars(select(Game).where(Game.app_id == 77860001)))) == 1
