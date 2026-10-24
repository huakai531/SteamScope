"""Synthetic 3B HTTP boundary. No live identities, achievements or friend edges."""

import httpx

from tests.steam_fixtures import APP, KEY
from tests.steam_fixtures import transport as base_transport

FRIEND = "76561198000000991"


def schema_payload():
    return {
        "game": {
            "appid": APP,
            "availableGameStats": {
                "achievements": [
                    {
                        "name": "FIRST",
                        "displayName": "First steps",
                        "description": "Finish the introduction",
                        "hidden": 0,
                    },
                    {
                        "name": "SECRET",
                        "displayName": "A hidden ending",
                        "description": "Synthetic spoiler",
                        "hidden": 1,
                    },
                ]
            },
        }
    }


def player_payload(identity):
    return {
        "playerstats": {
            "steamID": identity,
            "success": True,
            "achievements": [
                {"apiname": "FIRST", "achieved": 1, "unlocktime": 1700000000},
                {"apiname": "SECRET", "achieved": 0, "unlocktime": 0},
            ],
        }
    }


def friends_payload():
    return {
        "friendslist": {
            "friends": [
                {"steamid": FRIEND, "relationship": "friend", "friend_since": 1700000000},
                {"steamid": "76561198000000992", "relationship": "friend", "friend_since": 0},
            ]
        }
    }


def transport(request):
    assert request.url.host == "api.steampowered.com"
    assert request.headers["x-webapi-key"] == KEY and "key" not in request.url.params
    path = request.url.path
    if "GetSchemaForGame" in path:
        assert request.url.params["l"] == "english" and "steamid" not in request.url.params
        payload = schema_payload()
        payload["game"]["appid"] = int(request.url.params["appid"])
        return httpx.Response(200, json=payload)
    if "GetPlayerAchievements" in path:
        assert request.url.params["l"] == "english" and int(request.url.params["appid"]) >= APP
        payload = player_payload(request.url.params["steamid"])
        payload["playerstats"]["appid"] = int(request.url.params["appid"])
        return httpx.Response(200, json=payload)
    if "GetFriendList" in path:
        assert request.url.params["relationship"] == "friend"
        return httpx.Response(200, json=friends_payload())
    return base_transport(request)
