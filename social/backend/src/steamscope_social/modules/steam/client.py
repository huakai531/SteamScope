"""Fixed destinations, bounded transport and all-or-nothing snapshot validation."""

import asyncio
import json
import math
import re
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Literal
from urllib.parse import urlsplit

import httpx

from steamscope_social.core.config import Settings
from steamscope_social.modules.steam.payloads import AchievementData, DefinitionData, FriendData

Resource = Literal["profile", "library", "recent", "schema", "achievements", "friends"]
RESOURCES: tuple[Resource, ...] = ("profile", "library", "recent")
PATHS: dict[Resource, str] = {
    "profile": "/ISteamUser/GetPlayerSummaries/v2/",
    "library": "/IPlayerService/GetOwnedGames/v1/",
    "recent": "/IPlayerService/GetRecentlyPlayedGames/v1/",
    "schema": "/ISteamUserStats/GetSchemaForGame/v2/",
    "achievements": "/ISteamUserStats/GetPlayerAchievements/v1/",
    "friends": "/ISteamUser/GetFriendList/v1/",
}
MAX_BYTES = 4 * 1024 * 1024
MAX_GAMES = 20000


def valid_steam_id(value: object) -> bool:
    """Same public individual account range already enforced by verified OpenID."""
    return (
        isinstance(value, str)
        and bool(re.fullmatch(r"[0-9]{17}", value))
        and 76561197960265728 <= int(value) <= 76561202255233023
    )


def capability(
    settings: Settings,
) -> Literal["configured", "unconfigured", "invalid_configuration"]:
    value = settings.steam_api_key.get_secret_value()
    if not value:
        return "unconfigured"
    return "configured" if re.fullmatch(r"[0-9a-fA-F]{32}", value) else "invalid_configuration"


@dataclass(frozen=True)
class GameData:
    app_id: int
    name: str | None
    icon_hash: str | None
    total_minutes: int | None
    recent_minutes: int | None
    last_played_at: datetime | None


@dataclass(frozen=True)
class Snapshot:
    status: str
    code: str
    retry_after: int = 0
    games: tuple[GameData, ...] = ()
    persona: str | None = None
    profile_url: str | None = None
    avatar_url: str | None = None
    visibility: int | None = None
    definitions: tuple[DefinitionData, ...] = ()
    achievements: tuple[AchievementData, ...] = ()
    friends: tuple[FriendData, ...] = ()
    schema_revision: str | None = None
    diagnostics: tuple[tuple[str, str], ...] = ()


def integer(value: object, maximum: int = 2147483647) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError("invalid_integer")
    return value


def optional_int(data: dict[str, object], key: str) -> int | None:
    return integer(data[key]) if key in data else None


def optional_text(data: dict[str, object], key: str, limit: int) -> str | None:
    if key not in data:
        return None
    value = data[key]
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ValueError("invalid_text")
    return value


def mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise ValueError("invalid_object")
    return value


def map_response(resource: Resource, payload: object, steam_id: str, app_id: int = 0) -> Snapshot:
    """No partial parse can authorize reconciliation; unknown fields are discarded."""
    try:
        if resource in {"schema", "achievements", "friends"}:
            from steamscope_social.modules.steam.extended_mapping import map_extended

            return map_extended(resource, payload, steam_id, app_id)
        response = mapping(mapping(payload).get("response"))
        if resource == "profile":
            players = response.get("players")
            if players == []:
                return Snapshot("unknown", "PROFILE_UNAVAILABLE")
            if not isinstance(players, list) or len(players) != 1:
                raise ValueError("invalid_players")
            player = mapping(players[0])
            if player.get("steamid") != steam_id:
                return Snapshot("error", "IDENTITY_MISMATCH")
            visibility = integer(player.get("communityvisibilitystate"), 3)
            if visibility in {1, 2}:
                return Snapshot("restricted", "SOURCE_PROFILE_RESTRICTED", visibility=visibility)
            if visibility != 3:
                return Snapshot("unknown", "PROFILE_VISIBILITY_UNKNOWN")
            avatar = optional_text(player, "avatarfull", 512)
            if avatar:
                url = urlsplit(avatar)
                if (
                    url.scheme != "https"
                    or url.hostname
                    not in {
                        "avatars.steamstatic.com",
                        "avatars.akamai.steamstatic.com",
                        "steamcdn-a.akamaihd.net",
                        "cdn.akamai.steamstatic.com",
                    }
                    or url.port not in {None, 443}
                    or url.username
                    or url.password
                    or url.query
                    or url.fragment
                    or not re.fullmatch(r"/[A-Za-z0-9_./-]+", url.path)
                ):
                    avatar = None
            return Snapshot(
                "populated",
                "OK",
                persona=optional_text(player, "personaname", 128),
                profile_url="https://steamcommunity.com/profiles/" + steam_id + "/",
                avatar_url=avatar,
                visibility=visibility,
            )
        count_key = "game_count" if resource == "library" else "total_count"
        if count_key not in response:
            return Snapshot("unknown", "VISIBILITY_OR_DATA_UNKNOWN")
        count = integer(response[count_key], MAX_GAMES)
        games = response.get("games", [] if count == 0 else None)
        if not isinstance(games, list) or len(games) != count:
            raise ValueError("incomplete_snapshot")
        result: list[GameData] = []
        seen: set[int] = set()
        for item in games:
            game = mapping(item)
            app_id = integer(game.get("appid"), 4294967295)
            if app_id == 0 or app_id in seen:
                raise ValueError("invalid_or_duplicate_app")
            seen.add(app_id)
            last = optional_int(game, "rtime_last_played")
            if last and last > int(datetime.now(UTC).timestamp()) + 300:
                raise ValueError("future_playtime")
            icon = optional_text(game, "img_icon_url", 40)
            if icon and not re.fullmatch(r"[a-fA-F0-9]{40}", icon):
                icon = None
            result.append(
                GameData(
                    app_id,
                    optional_text(game, "name", 256),
                    icon,
                    optional_int(game, "playtime_forever"),
                    optional_int(game, "playtime_2weeks"),
                    datetime.fromtimestamp(last, UTC) if last else None,
                )
            )
        return Snapshot("populated" if count else "empty", "OK", games=tuple(result))
    except (ValueError, TypeError, OverflowError):
        return Snapshot("error", "INVALID_RESPONSE")


def retry_delay(value: str | None) -> int | None:
    try:
        if value and value.isdigit():
            if len(value) > 10 or int(value) > 2147483647:
                return None
            return max(1, int(value))
        if value:
            delay = math.ceil((parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
            return max(1, delay) if delay <= 2147483647 else None
    except (ValueError, TypeError, OverflowError):
        pass
    return 60


async def details_response(
    response: httpx.Response, resource: Resource, steam_id: str, app_id: int
) -> Snapshot:
    """Bounded evidence, never raw errors/headers/URLs/identities. No extra HTTP request."""
    media = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    media = (
        media
        if media
        in {
            "application/json",
            "text/json",
            "text/plain",
            "text/html",
            "application/xml",
            "text/xml",
            "application/octet-stream",
        }
        else "other"
        if media
        else "missing"
    )
    meta = {"http_status": str(response.status_code), "content_type": media}
    status = response.status_code
    if status not in {200, 401, 403}:
        # Do not delay an authoritative Retry-After by waiting for an error body.
        if status == 429:
            delay = retry_delay(response.headers.get("Retry-After"))
            result = (
                Snapshot("unavailable", "RETRY_AFTER_OUT_OF_RANGE")
                if delay is None
                else Snapshot("retry", "UPSTREAM_RATE_LIMIT", delay)
            )
        else:
            result = (
                Snapshot("retry", "UPSTREAM_UNAVAILABLE")
                if status >= 500
                else Snapshot("error", "UPSTREAM_REJECTED")
            )
        return replace(result, diagnostics=tuple({**meta, "body": "not_read"}.items()))
    data = bytearray()
    limit = MAX_BYTES if response.status_code == 200 else 65536
    truncated = False
    read_failed = False
    try:
        async with asyncio.timeout(10 if status == 200 else 2):
            async for chunk in response.aiter_bytes():
                if len(data) + len(chunk) > limit:
                    truncated = True
                    break
                data.extend(chunk)
    except (httpx.HTTPError, TimeoutError):
        if status == 200:
            raise
        read_failed = True
    payload: object = None
    meta["body"] = "read_failed" if read_failed else "too_large" if truncated else "invalid_json"
    if not truncated and not read_failed:
        try:
            payload = json.loads(data)
            meta["body"] = "json"
        except (ValueError, UnicodeError, RecursionError):
            pass
    section = {"schema": "game", "achievements": "playerstats", "friends": "friendslist"}[resource]
    fields = payload.get(section) if isinstance(payload, dict) else None
    fields = fields if isinstance(fields, dict) else {}
    success = fields.get("success")
    meta["business_success"] = (
        str(success).lower()
        if type(success) is bool
        else "invalid"
        if "success" in fields
        else "absent"
    )
    error = fields.get("error")
    # Only exact allowlisted phrases become codes. Unrecognized text might contain credentials.
    known_errors = {
        "Profile is not public": "PROFILE_NOT_PUBLIC",
        "Requested app has no stats": "APP_HAS_NO_STATS",
        "Invalid API key": "INVALID_API_KEY",
    }
    meta["business_error"] = (
        known_errors.get(error, "UNRECOGNIZED")
        if isinstance(error, str)
        else "UNRECOGNIZED"
        if "error" in fields
        else "absent"
    )
    if status in {401, 403}:
        code = (
            "FRIENDS_PRIVATE_OR_UNAUTHORIZED"
            if resource == "friends" and status == 401
            else "ACCESS_DENIED_" + resource.upper()
        )
        result = Snapshot("unavailable", code)
    elif truncated:
        result = Snapshot("error", "RESPONSE_TOO_LARGE")
    elif meta["body"] != "json":
        result = Snapshot("error", "INVALID_RESPONSE")
    else:
        result = map_response(resource, payload, steam_id, app_id)
    return replace(result, diagnostics=tuple(meta.items()))


@dataclass
class SteamClient:
    settings: Settings = field(repr=False)
    transport: httpx.AsyncBaseTransport | None = field(default=None, repr=False)

    async def fetch(self, resource: Resource, steam_id: str, app_id: int = 0) -> Snapshot:
        if capability(self.settings) != "configured":
            return Snapshot("configuration", "STEAM_SYNC_NOT_CONFIGURED")
        if not valid_steam_id(steam_id) or resource not in PATHS:
            return Snapshot("error", "INVALID_IDENTITY")
        # A test key can never reach the live service, even if a test forgets its transport.
        if self.settings.environment == "test" and self.transport is None:
            return Snapshot("configuration", "TEST_TRANSPORT_REQUIRED")
        params = {"format": "json"}
        if resource in {"schema", "achievements"}:
            if type(app_id) is not int or not 0 < app_id <= 4294967295:
                return Snapshot("error", "INVALID_APP")
            params.update(appid=str(app_id), l="english")
            if resource == "achievements":
                params["steamid"] = steam_id
        elif resource == "friends":
            params.update(steamid=steam_id, relationship="friend")
        elif resource == "profile":
            params["steamids"] = steam_id
        else:
            arguments: dict[str, object] = {"steamid": steam_id}
            if resource == "library":
                arguments.update(include_appinfo=True, include_played_free_games=True)
            else:
                arguments["count"] = 0
            params["input_json"] = json.dumps(arguments, separators=(",", ":"))
        try:
            async with (
                asyncio.timeout(10),
                httpx.AsyncClient(
                    transport=self.transport,
                    verify=True,
                    trust_env=False,
                    follow_redirects=False,
                    timeout=httpx.Timeout(5, connect=3),
                ) as client,
            ):
                async with client.stream(
                    "GET",
                    "https://api.steampowered.com" + PATHS[resource],
                    params=params,
                    headers={
                        "x-webapi-key": self.settings.steam_api_key.get_secret_value(),
                        "Accept": "application/json",
                    },
                ) as response:
                    if resource in {"schema", "achievements", "friends"}:
                        return await details_response(response, resource, steam_id, app_id)
                    if response.status_code == 429:
                        delay = retry_delay(response.headers.get("Retry-After"))
                        if delay is None:
                            return Snapshot("unavailable", "RETRY_AFTER_OUT_OF_RANGE")
                        return Snapshot(
                            "retry",
                            "UPSTREAM_RATE_LIMIT",
                            delay,
                        )
                    if response.status_code >= 500:
                        return Snapshot("retry", "UPSTREAM_UNAVAILABLE")
                    if response.status_code in {401, 403}:
                        if resource == "friends" and response.status_code == 401:
                            return Snapshot("unavailable", "FRIENDS_PRIVATE_OR_UNAUTHORIZED")
                        # These endpoints do not document a definitive key-vs-privacy signal.
                        return Snapshot("unavailable", "ACCESS_DENIED_" + resource.upper())
                    if response.status_code != 200:
                        return Snapshot("error", "UPSTREAM_REJECTED")
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > MAX_BYTES:
                            return Snapshot("error", "RESPONSE_TOO_LARGE")
                    return map_response(resource, json.loads(data), steam_id, app_id)
        except (httpx.HTTPError, TimeoutError):
            # Never stringify an HTTP exception (URL/header may contain credentials).
            return Snapshot("retry", "UPSTREAM_TIMEOUT_OR_NETWORK")
        except (ValueError, UnicodeError, RecursionError):
            return Snapshot("error", "INVALID_RESPONSE")
