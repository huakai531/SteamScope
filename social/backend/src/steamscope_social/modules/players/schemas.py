from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from steamscope_social.modules.steam.schemas import AchievementView


class PlayerState(BaseModel):
    status: str
    data_available: bool = False
    stale: bool = False
    last_success_at: datetime | None = None
    in_progress: bool = False


class PlayerProgress(BaseModel):
    state: PlayerState
    coverage: str = "unknown"
    definition_count: int | None = None
    known_unlocked: int | None = None
    known_locked: int | None = None
    completion_percent: float | None = None


class PlayerGame(BaseModel):
    app_id: int
    name: str | None
    total_minutes: int | None = None
    recent_minutes: int | None = None
    last_played_at: datetime | None = None
    achievements: PlayerProgress


class PlayerProfile(BaseModel):
    handle: str
    display_name: str
    biography: str
    is_owner: bool
    # Locale/timezone are owner-only until separate public consent exists.
    locale: str | None = None
    timezone: str | None = None
    persona_name: str | None = None
    steam_profile_url: str | None = None
    profile_state: PlayerState
    library_state: PlayerState
    playtime_visible: bool
    achievements_visible: bool
    recent_state: PlayerState
    game_count: int | None = None
    total_minutes: int | None = None
    synchronized_achievement_games: int | None = None
    most_played: list[PlayerGame] = Field(default_factory=list)
    recent_games: list[PlayerGame] = Field(default_factory=list)


class PlayerLibrary(BaseModel):
    state: PlayerState
    playtime_visible: bool
    achievements_visible: bool
    items: list[PlayerGame]
    total_count: int | None = None
    next_cursor: str | None = None


class PlayerGameDetail(BaseModel):
    handle: str
    library_state: PlayerState
    playtime_visible: bool
    game: PlayerGame


class PlayerAchievements(BaseModel):
    app_id: int
    progress: PlayerProgress
    items: list[AchievementView]
    next_cursor: str | None = None


class MutualGame(BaseModel):
    app_id: int
    name: str | None
    left_minutes: int | None
    right_minutes: int | None
    difference_minutes: int | None
    left_recent_minutes: int | None
    right_recent_minutes: int | None
    left_achievements: PlayerProgress
    right_achievements: PlayerProgress
    left_completion: float | None = None
    right_completion: float | None = None


class PlayerComparison(BaseModel):
    left_handle: str
    right_handle: str
    status: Literal["available", "unavailable"]
    left_library_state: PlayerState
    right_library_state: PlayerState
    items: list[MutualGame]
    mutual_count: int | None = None
    left_total_minutes: int | None = None
    right_total_minutes: int | None = None
    comparable_achievement_games: int | None = None
    next_cursor: str | None = None
