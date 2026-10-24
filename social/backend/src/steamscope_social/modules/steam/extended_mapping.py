"""Endpoint-specific strict snapshots. Schema `name` matches player `apiname`."""

import re
from datetime import UTC, datetime
from urllib.parse import urlsplit

from steamscope_social.modules.steam.client import (
    Snapshot,
    integer,
    mapping,
    optional_text,
    valid_steam_id,
)
from steamscope_social.modules.steam.payloads import AchievementData, DefinitionData, FriendData

MAX_ENTRIES = 10000


def timestamp(data: dict[str, object], name: str) -> datetime | None:
    if name not in data:
        return None
    value = integer(data[name], 4294967295)
    if value > int(datetime.now(UTC).timestamp()) + 300:
        raise ValueError("future_timestamp")
    return datetime.fromtimestamp(value, UTC) if value else None


def identifier(data: dict[str, object], name: str) -> str:
    value = optional_text(data, name, 128)
    if not value or not value.strip():
        raise ValueError("missing_identifier")
    return value


def icon(data: dict[str, object], name: str) -> str | None:
    value = optional_text(data, name, 512)
    if not value:
        return None
    url = urlsplit(value)
    if (
        url.scheme != "https"
        or url.hostname
        not in {
            "cdn.akamai.steamstatic.com",
            "steamcdn-a.akamaihd.net",
            "cdn.cloudflare.steamstatic.com",
            "shared.akamai.steamstatic.com",
            "shared.fastly.steamstatic.com",
            "steamcommunity-a.akamaihd.net",
        }
        or url.port not in {None, 443}
        or url.username
        or url.password
        or url.query
        or url.fragment
        or not re.fullmatch(r"/[A-Za-z0-9_./-]+", url.path)
        or ".." in url.path
    ):
        return None
    return value


def validate_identity(data: dict[str, object], steam_id: str, app_id: int) -> None:
    if "steamID" in data and data["steamID"] != steam_id:
        raise ValueError("identity_mismatch")
    if "steamid" in data and data["steamid"] != steam_id:
        raise ValueError("identity_mismatch")
    for key in ("appid", "gameid"):
        if key in data and not (
            type(data[key]) is int
            and data[key] == app_id
            or isinstance(data[key], str)
            and data[key] == str(app_id)
        ):
            raise ValueError("app_mismatch")


def entries(value: object) -> list[object]:
    if not isinstance(value, list) or len(value) > MAX_ENTRIES:
        raise ValueError("invalid_or_excessive_list")
    return value


def map_extended(resource: str, payload: object, steam_id: str, app_id: int) -> Snapshot:
    root = mapping(payload)
    if resource == "schema":
        game = mapping(root.get("game"))
        validate_identity(game, steam_id, app_id)
        if "success" in game and game["success"] is not True:
            return Snapshot("unavailable", "SCHEMA_UNAVAILABLE")
        if "availableGameStats" not in game:
            return Snapshot("unknown", "SCHEMA_SUPPORT_UNKNOWN")
        stats = mapping(game["availableGameStats"])
        # Only an explicit array confirms absence. Missing data is not a no-achievement game.
        if "achievements" not in stats:
            return Snapshot("unknown", "SCHEMA_SUPPORT_UNKNOWN")
        definitions = []
        seen = set()
        for item in entries(stats["achievements"]):
            row = mapping(item)
            name = identifier(row, "name")
            if name in seen:
                raise ValueError("duplicate_definition")
            seen.add(name)
            hidden = integer(row.get("hidden"), 1)
            definitions.append(
                DefinitionData(
                    name,
                    optional_text(row, "displayName", 256),
                    optional_text(row, "description", 2048),
                    bool(hidden),
                    icon(row, "icon"),
                    icon(row, "icongray"),
                )
            )
        return Snapshot(
            "populated" if definitions else "empty", "OK", definitions=tuple(definitions)
        )
    if resource == "achievements":
        player = mapping(root.get("playerstats"))
        validate_identity(player, steam_id, app_id)
        if player.get("success") is False:
            return Snapshot("unavailable", "PLAYER_PROGRESS_UNAVAILABLE")
        if player.get("success") is not True or "achievements" not in player:
            return Snapshot("unknown", "PLAYER_COVERAGE_UNKNOWN")
        achievements = []
        seen = set()
        for item in entries(player["achievements"]):
            row = mapping(item)
            name = identifier(row, "apiname")
            if name in seen:
                raise ValueError("duplicate_player_identifier")
            seen.add(name)
            unlocked = bool(integer(row["achieved"], 1)) if "achieved" in row else None
            when = timestamp(row, "unlocktime")
            if when is not None and unlocked is not True:
                raise ValueError("inconsistent_unlock_time")
            achievements.append(AchievementData(name, unlocked, when))
        return Snapshot(
            "populated" if achievements else "empty", "OK", achievements=tuple(achievements)
        )
    friends = mapping(root.get("friendslist"))
    validate_identity(friends, steam_id, app_id)
    if "success" in friends and friends["success"] is not True:
        return Snapshot("unavailable", "FRIENDS_UNAVAILABLE")
    if "friends" not in friends or friends.get("has_more") or friends.get("next_cursor"):
        return Snapshot("unknown", "FRIEND_COVERAGE_UNKNOWN")
    result = []
    seen = set()
    for item in entries(friends["friends"]):
        row = mapping(item)
        identity = row.get("steamid")
        if (
            not isinstance(identity, str)
            or not valid_steam_id(identity)
            or identity == steam_id
            or identity in seen
            or row.get("relationship") != "friend"
        ):
            raise ValueError("invalid_friend")
        seen.add(identity)
        result.append(FriendData(identity, timestamp(row, "friend_since")))
    if "total_count" in friends and integer(friends["total_count"], MAX_ENTRIES) != len(result):
        raise ValueError("incomplete_friends")
    return Snapshot("populated" if result else "empty", "OK", friends=tuple(result))
