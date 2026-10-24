"""Synthetic transport only. No real identities, API keys, URLs or private libraries."""

import json

import httpx

KEY = "a" * 32
APP = 77730001


def transport(request: httpx.Request) -> httpx.Response:
    assert request.url.host == "api.steampowered.com"
    assert request.headers["x-webapi-key"] == KEY
    assert "key" not in request.url.params
    if "GetPlayerSummaries" in request.url.path:
        return httpx.Response(
            200,
            json={
                "response": {
                    "players": [
                        {
                            "steamid": request.url.params["steamids"],
                            "personaname": "Synthetic Steam persona",
                            "communityvisibilitystate": 3,
                            "ignored_new_field": "not persisted",
                        }
                    ]
                }
            },
        )
    args = json.loads(request.url.params["input_json"])
    games = [
        {
            "appid": APP + i,
            "name": f"Synthetic Game {i + 1}",
            "playtime_forever": i * 61,
            "playtime_2weeks": i * 3,
        }
        for i in range(27)
    ]
    if "GetOwnedGames" in request.url.path:
        assert args["include_appinfo"] is True and args["include_played_free_games"] is True
        assert "appids_filter" not in args
        return httpx.Response(200, json={"response": {"game_count": len(games), "games": games}})
    assert args["count"] == 0 and "GetRecentlyPlayedGames" in request.url.path
    return httpx.Response(200, json={"response": {"total_count": 1, "games": games[1:2]}})
