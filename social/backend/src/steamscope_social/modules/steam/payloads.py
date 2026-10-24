"""Validated, bounded values; never stores a raw upstream response."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DefinitionData:
    api_name: str
    display_name: str | None
    description: str | None
    hidden: bool
    icon_url: str | None
    icon_gray_url: str | None


@dataclass(frozen=True)
class AchievementData:
    api_name: str
    unlocked: bool | None
    unlocked_at: datetime | None


@dataclass(frozen=True)
class FriendData:
    steam_id: str
    since: datetime | None
