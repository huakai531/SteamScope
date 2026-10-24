import httpx
import pytest
from pydantic import SecretStr

from steamscope_social.modules.steam.client import SteamClient, map_response
from tests.steam_details_fixtures import friends_payload, player_payload, schema_payload, transport
from tests.steam_fixtures import APP, KEY

OWNER = "76561198000000123"


@pytest.mark.parametrize(
    "identity", ["76561197960265728", "76561200000000000", "76561202255233023"]
)
async def test_entire_verified_individual_identity_range(settings, identity):
    settings.steam_api_key = SecretStr(KEY)
    client = SteamClient(settings, httpx.MockTransport(transport))
    for resource in ("profile", "friends", "achievements"):
        assert (await client.fetch(resource, identity, APP)).status == "populated"
    friends = friends_payload()
    friends["friendslist"]["friends"][0]["steamid"] = "76561202255233023"
    assert map_response("friends", friends, OWNER).status == "populated"


@pytest.mark.parametrize(
    "identity",
    [
        "76561197960265727",
        "76561202255233024",
        "00000000000000000",
        "765612000000000000",
        "7656120000000000x",
    ],
)
async def test_out_of_range_ids_rejected_before_http(settings, identity):
    settings.steam_api_key = SecretStr(KEY)

    def forbidden(_):
        raise AssertionError("invalid ID must not request HTTP")

    assert (
        await SteamClient(settings, httpx.MockTransport(forbidden)).fetch("friends", identity)
    ).code == "INVALID_IDENTITY"


def test_identifiers_differ_and_zero_or_absent_times_remain_unknown():
    schema = map_response("schema", schema_payload(), OWNER, APP)
    player = player_payload(OWNER)
    player["playerstats"]["achievements"][0]["unlocktime"] = 0
    result = map_response("achievements", player, OWNER, APP)
    assert schema.definitions[0].api_name == result.achievements[0].api_name == "FIRST"
    assert result.achievements[0].unlocked is True and result.achievements[0].unlocked_at is None
    player["playerstats"]["achievements"][0].pop("unlocktime")
    player["playerstats"]["achievements"][0].pop("achieved")
    unknown = map_response("achievements", player, OWNER, APP).achievements[0]
    assert unknown.unlocked is None and unknown.unlocked_at is None
    assert map_response("friends", friends_payload(), OWNER).friends[1].since is None


@pytest.mark.parametrize(
    "resource,payload,status",
    [
        ("schema", {"game": {"availableGameStats": {"achievements": []}}}, "empty"),
        ("schema", {"game": {}}, "unknown"),
        ("schema", {"game": {"availableGameStats": {}}}, "unknown"),
        ("schema", {"game": {"success": False}}, "unavailable"),
        (
            "achievements",
            {"playerstats": {"success": False, "error": "private or unavailable"}},
            "unavailable",
        ),
        ("achievements", {"playerstats": {"success": True}}, "unknown"),
        ("achievements", {"playerstats": {"success": True, "achievements": []}}, "empty"),
        ("friends", {"friendslist": {"friends": []}}, "empty"),
        ("friends", {"friendslist": {}}, "unknown"),
        ("friends", {"friendslist": {"friends": [], "has_more": True}}, "unknown"),
        ("friends", {"friendslist": {"friends": [], "total_count": 1}}, "error"),
    ],
)
def test_empty_unknown_and_application_failure_are_distinct(resource, payload, status):
    assert map_response(resource, payload, OWNER, APP).status == status


@pytest.mark.parametrize(
    "kind",
    [
        "schema_duplicate",
        "player_duplicate",
        "friend_duplicate",
        "identity",
        "appid",
        "future",
        "boolean",
        "negative",
        "wrong_relationship",
        "self",
        "oversized",
        "missing_identifier",
    ],
)
def test_invalid_complete_snapshots_are_rejected(kind):
    resource, payload = "achievements", player_payload(OWNER)
    if kind == "schema_duplicate":
        resource, payload = "schema", schema_payload()
        payload["game"]["availableGameStats"]["achievements"] *= 2
    elif kind == "player_duplicate":
        payload["playerstats"]["achievements"] *= 2
    elif kind in {"friend_duplicate", "wrong_relationship", "self"}:
        resource, payload = "friends", friends_payload()
        if kind == "friend_duplicate":
            payload["friendslist"]["friends"] *= 2
        elif kind == "self":
            payload["friendslist"]["friends"][0]["steamid"] = OWNER
        else:
            payload["friendslist"]["friends"][0]["relationship"] = "blocked"
    elif kind == "identity":
        payload["playerstats"]["steamID"] = "76561198000000124"
    elif kind == "appid":
        payload["playerstats"]["appid"] = APP + 1
    elif kind == "future":
        payload["playerstats"]["achievements"][0]["unlocktime"] = 4294967295
    elif kind == "boolean":
        payload["playerstats"]["achievements"][0]["achieved"] = True
    elif kind == "negative":
        payload["playerstats"]["achievements"][0]["unlocktime"] = -1
    elif kind == "oversized":
        payload["playerstats"]["achievements"] *= 5001
    elif kind == "missing_identifier":
        payload["playerstats"]["achievements"][0].pop("apiname")
    assert map_response(resource, payload, OWNER, APP).status == "error"


def test_unsafe_icons_are_not_remote_proxy_inputs():
    data = schema_payload()
    data["game"]["availableGameStats"]["achievements"][0]["icon"] = (
        "https://attacker.invalid/icon.png"
    )
    result = map_response("schema", data, OWNER, APP)
    assert result.status == "populated" and result.definitions[0].icon_url is None


@pytest.mark.parametrize("resource", ["schema", "achievements", "friends"])
async def test_official_paths_parameters_and_no_test_live_fallback(settings, resource):
    settings.steam_api_key = SecretStr(KEY)
    result = await SteamClient(settings, httpx.MockTransport(transport)).fetch(resource, OWNER, APP)
    assert result.status == "populated"
    assert (
        await SteamClient(settings).fetch(resource, OWNER, APP)
    ).code == "TEST_TRANSPORT_REQUIRED"


@pytest.mark.parametrize(
    "status,code", [(401, "FRIENDS_PRIVATE_OR_UNAUTHORIZED"), (403, "ACCESS_DENIED_FRIENDS")]
)
async def test_friend_auth_errors_do_not_globally_invalidate_key(settings, status, code):
    settings.steam_api_key = SecretStr(KEY)
    result = await SteamClient(
        settings, httpx.MockTransport(lambda _: httpx.Response(status))
    ).fetch("friends", OWNER)
    assert result.status == "unavailable" and result.code == code


@pytest.mark.parametrize("status", [200, 401, 403])
async def test_player_failure_evidence_is_safe_and_preserves_http_status(settings, status):
    settings.steam_api_key = SecretStr(KEY)
    calls = []

    def denied(request):
        calls.append(request)
        assert request.method == "GET" and request.url.host == "api.steampowered.com"
        assert request.url.path == "/ISteamUserStats/GetPlayerAchievements/v1/"
        assert dict(request.url.params) == {
            "format": "json",
            "steamid": OWNER,
            "appid": str(APP),
            "l": "english",
        }
        assert request.headers["x-webapi-key"] == KEY and "key" not in request.url.params
        return httpx.Response(
            status, json={"playerstats": {"success": False, "error": "Profile is not public"}}
        )

    result = await SteamClient(settings, httpx.MockTransport(denied)).fetch(
        "achievements", OWNER, APP
    )
    meta = dict(result.diagnostics)
    assert len(calls) == 1 and result.status == "unavailable"
    assert result.code == (
        "PLAYER_PROGRESS_UNAVAILABLE" if status == 200 else "ACCESS_DENIED_ACHIEVEMENTS"
    )
    assert meta == {
        "http_status": str(status),
        "content_type": "application/json",
        "body": "json",
        "business_success": "false",
        "business_error": "PROFILE_NOT_PUBLIC",
    }


@pytest.mark.parametrize(
    "mode", ["unknown_json", "html", "oversized", "read_failure", "rate_limit"]
)
async def test_diagnostic_capture_never_retains_raw_sensitive_values(settings, mode):
    settings.steam_api_key = SecretStr(KEY)

    class Broken(httpx.AsyncByteStream):
        async def __aiter__(self):
            raise httpx.ReadError("must not be retained " + KEY)
            yield b""  # pragma: no cover

    def response(_):
        if mode == "unknown_json":
            return httpx.Response(
                403, json={"playerstats": {"success": False, "error": KEY + OWNER}}
            )
        if mode == "html":
            return httpx.Response(
                403, content=KEY + OWNER, headers={"Content-Type": "text/html; charset=UTF-8"}
            )
        if mode == "oversized":
            return httpx.Response(403, content=b"x" * 65537)
        return httpx.Response(
            429 if mode == "rate_limit" else 403, stream=Broken(), headers={"Retry-After": "90000"}
        )

    result = await SteamClient(settings, httpx.MockTransport(response)).fetch(
        "achievements", OWNER, APP
    )
    meta = dict(result.diagnostics)
    assert KEY not in repr(meta) and OWNER not in repr(meta)
    if mode == "rate_limit":
        assert result.retry_after == 90000 and meta["body"] == "not_read"
    else:
        assert result.code == "ACCESS_DENIED_ACHIEVEMENTS" and meta["http_status"] == "403"
        assert meta["business_error"] == ("UNRECOGNIZED" if mode == "unknown_json" else "absent")
        assert (
            meta["body"]
            == {
                "unknown_json": "json",
                "html": "invalid_json",
                "oversized": "too_large",
                "read_failure": "read_failed",
            }[mode]
        )
