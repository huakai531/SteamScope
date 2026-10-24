import json
from dataclasses import asdict

import httpx
import pytest
from pydantic import SecretStr

from steamscope_social.modules.steam.client import (
    MAX_BYTES,
    SteamClient,
    capability,
    map_response,
    retry_delay,
)
from tests.steam_fixtures import KEY, transport

ID = "76561198000000001"


def test_long_retry_after_is_not_shortened_to_one_day():
    assert retry_delay("172800") == 172800
    assert retry_delay("9" * 100) is None
    assert retry_delay(None) == 60


@pytest.mark.parametrize("resource", ["profile", "library", "recent"])
async def test_real_client_maps_transport_and_documented_parameters(settings, resource):
    settings.steam_api_key = SecretStr(KEY)
    result = await SteamClient(settings, httpx.MockTransport(transport)).fetch(resource, ID)
    assert result.status == "populated"
    assert KEY not in repr(result)
    assert "ignored_new_field" not in repr(result)


@pytest.mark.parametrize(
    "body,status",
    [
        ({}, "unknown"),
        ({"game_count": 0}, "empty"),
        ({"game_count": 0, "games": []}, "empty"),
        ({"game_count": 1, "games": []}, "error"),
        ({"game_count": True}, "error"),
        ({"game_count": 2, "games": [{"appid": 1}, {"appid": 1}]}, "error"),
        ({"game_count": 1, "games": [{"appid": 0}]}, "error"),
        ({"game_count": 1, "games": [{"appid": 1, "playtime_forever": -1}]}, "error"),
        ({"game_count": 1, "games": [{"appid": "1"}]}, "error"),
        ({"game_count": 1, "games": [{"appid": 1, "playtime_forever": True}]}, "error"),
        ({"game_count": 1, "games": [{"appid": 1, "rtime_last_played": 2147483647}]}, "error"),
    ],
)
def test_complete_empty_ambiguous_or_invalid_snapshot(body, status):
    assert map_response("library", {"response": body}, ID).status == status


def test_missing_is_not_zero_and_persona_is_plain_data():
    result = map_response(
        "library",
        {
            "response": {
                "game_count": 2,
                "games": [
                    {"appid": 1},
                    {"appid": 2, "playtime_forever": 0, "playtime_2weeks": 0},
                ],
            }
        },
        ID,
    )
    assert result.games[0].total_minutes is None and result.games[0].last_played_at is None
    assert result.games[1].total_minutes == result.games[1].recent_minutes == 0
    result = map_response(
        "profile",
        {
            "response": {
                "players": [
                    {
                        "steamid": ID,
                        "communityvisibilitystate": 3,
                        "personaname": "<script>{**/*}</script>",
                        "avatarfull": "https://attacker.invalid/private",
                        "realname": "DO_NOT_KEEP",
                    }
                ]
            }
        },
        ID,
    )
    assert result.persona == "<script>{**/*}</script>" and result.avatar_url is None
    assert "DO_NOT_KEEP" not in repr(asdict(result))


@pytest.mark.parametrize(
    "visibility,status", [(1, "restricted"), (2, "restricted"), (3, "populated"), (0, "unknown")]
)
def test_profile_classification_only_applies_to_profile(visibility, status):
    payload = {"response": {"players": [{"steamid": ID, "communityvisibilitystate": visibility}]}}
    assert map_response("profile", payload, ID).status == status
    assert map_response("profile", payload, "76561198000000002").code == "IDENTITY_MISMATCH"


@pytest.mark.parametrize("resource", ["profile", "library", "recent"])
@pytest.mark.parametrize(
    "status,expected",
    [(401, "unavailable"), (403, "unavailable"), (429, "retry"), (500, "retry"), (302, "error")],
)
async def test_endpoint_aware_http_errors(settings, resource, status, expected):
    settings.steam_api_key = SecretStr(KEY)

    def response(request):
        return httpx.Response(status, headers={"Retry-After": "120"}, text=KEY)

    result = await SteamClient(settings, httpx.MockTransport(response)).fetch(resource, ID)
    assert result.status == expected and KEY not in repr(result)
    if status in {401, 403}:
        assert result.code == "ACCESS_DENIED_" + resource.upper()
    if status == 429:
        assert result.retry_after == 120


async def test_bounded_malformed_timeout_and_secret_redaction(settings, caplog):
    settings.steam_api_key = SecretStr(KEY)
    for response, code in [
        (b"{bad", "INVALID_RESPONSE"),
        (b"x" * (MAX_BYTES + 1), "RESPONSE_TOO_LARGE"),
    ]:
        result = await SteamClient(
            settings,
            httpx.MockTransport(lambda r, body=response: httpx.Response(200, content=body)),
        ).fetch("library", ID)
        assert result.code == code

    def timeout(request):
        raise httpx.ReadTimeout("key=" + KEY, request=request)

    result = await SteamClient(settings, httpx.MockTransport(timeout)).fetch("profile", ID)
    assert result.status == "retry" and KEY not in repr(result) + caplog.text


async def test_configuration_never_sends_dummy_key_live(settings):
    assert capability(settings) == "unconfigured"
    assert (await SteamClient(settings).fetch("profile", ID)).status == "configuration"
    settings.steam_api_key = SecretStr("bad")
    assert capability(settings) == "invalid_configuration"
    settings.steam_api_key = SecretStr(KEY)
    assert (await SteamClient(settings).fetch("profile", ID)).code == "TEST_TRANSPORT_REQUIRED"


def test_recent_count_zero_is_complete_but_missing_count_is_unknown():
    assert map_response("recent", {"response": {"total_count": 0}}, ID).status == "empty"
    assert map_response("recent", {"response": {}}, ID).status == "unknown"
    assert json.dumps(asdict(map_response("profile", {}, ID)))
