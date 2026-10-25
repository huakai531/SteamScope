from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from steamscope_social.modules.steam.visuals import GameVisual


class ResourceView(BaseModel):
    resource: str
    status: str
    code: str
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    snapshot_id: UUID | None = None
    stale: bool = False
    in_progress: bool = False
    data_available: bool = False


class JobView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    status: str
    attempts: int
    created_at: datetime
    available_at: datetime
    finished_at: datetime | None
    outcomes: dict[str, str]
    scope: str
    app_id: int


class RunView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    attempt: int
    started_at: datetime
    finished_at: datetime | None
    status: str
    outcomes: dict[str, str]


class JobDetail(BaseModel):
    job: JobView
    runs: list[RunView]


class EnqueuedView(BaseModel):
    job: JobView
    reused: bool


class SyncStatusView(BaseModel):
    capability: Literal["configured", "unconfigured", "invalid_configuration"]
    operator_instruction: str | None
    resources: list[ResourceView]
    latest_job: JobView | None
    cooldown_until: datetime | None


class SteamProfileView(BaseModel):
    state: ResourceView
    persona_name: str | None
    profile_url: str | None
    avatar_url: str | None
    source_visibility: int | None


class GameView(BaseModel):
    visual: GameVisual = Field(default_factory=GameVisual)
    app_id: int
    name: str | None
    total_minutes: int | None
    recent_minutes: int | None
    last_played_at: datetime | None = None


class GamesView(BaseModel):
    state: ResourceView
    items: list[GameView]
    next_after: int | None = None
    returned_game_count: int | None = None
    total_minutes: int | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None


class ClearSteamData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: Literal["CLEAR STEAM DATA"]


class SchemaView(BaseModel):
    language: Literal["english"] = "english"
    status: str
    code: str
    revision: str | None
    last_success_at: datetime | None
    stale: bool


class AchievementView(BaseModel):
    api_name: str
    display_name: str | None
    description: str | None
    hidden: bool
    definition_available: bool
    unlocked: bool | None
    unlocked_at: datetime | None


class AchievementsView(BaseModel):
    app_id: int
    state: ResourceView
    schema_state: SchemaView
    latest_job: JobView | None
    coverage: Literal["unknown", "complete", "partial", "no_achievements", "stale"]
    known_unlocked: int | None
    known_locked: int | None
    definition_count: int | None
    completion_percent: float | None
    items: list[AchievementView]
    next_after: str | None = None


class FriendView(BaseModel):
    steam_id64: str
    profile_url: str
    friend_since: datetime | None


class FriendsView(BaseModel):
    state: ResourceView
    latest_job: JobView | None
    total_count: int | None
    items: list[FriendView]
    next_after: str | None = None
