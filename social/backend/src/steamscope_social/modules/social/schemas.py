from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Reason = Literal[
    "harassment", "spam", "impersonation", "inappropriate_content", "suspicious_behavior", "other"
]


class TargetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    handle: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{2,23}$")


class ReportInput(TargetInput):
    reason: Reason
    description: str = Field(default="", max_length=1000)


class Person(BaseModel):
    avatar_url: str | None = None
    handle: str
    display_name: str


class SocialRelationship(BaseModel):
    status: Literal["self", "none", "incoming", "outgoing", "connected"]
    request_id: UUID | None = None
    can_request: bool = False


class RequestView(BaseModel):
    id: UUID
    person: Person | None
    direction: Literal["incoming", "outgoing"]
    status: str
    created_at: datetime
    expires_at: datetime


class RequestList(BaseModel):
    items: list[RequestView]
    next_cursor: str | None = None


class PersonList(BaseModel):
    items: list[Person]
    next_cursor: str | None = None


class NotificationView(BaseModel):
    id: UUID
    kind: str
    person: Person | None
    request_id: UUID
    created_at: datetime
    read_at: datetime | None


class NotificationList(BaseModel):
    items: list[NotificationView]
    next_cursor: str | None = None


class ReportReceipt(BaseModel):
    id: UUID
    status: str


class Recommendation(BaseModel):
    person: Person
    score: int
    mutual_games: int | None
    recent_overlap: int | None
    reasons: list[str]
    steam_friend: bool = False


class DiscoveryList(BaseModel):
    items: list[Recommendation]
    # Bounded deterministic pool; no total user count or exhaustive pagination.
    policy: Literal["visible-evidence-v1"] = "visible-evidence-v1"
