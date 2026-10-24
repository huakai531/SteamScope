import unicodedata
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from steamscope_social.modules.social.schemas import Person


class DirectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    handle: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{2,23}$")


class SendInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_message_id: UUID
    body: str = Field(min_length=1, max_length=2000)

    @field_validator("body")
    @classmethod
    def text_only(cls, value: str) -> str:
        value = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
        if not value.strip() or len(value) > 2000 or value.count("\n") > 50:
            raise ValueError("Message must contain 1–2000 characters and at most 50 newlines")
        if any(unicodedata.category(c) in {"Cs", "Cc"} and c not in "\n\t" for c in value):
            raise ValueError("Unsupported control character")
        return value


class ReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sequence: int = Field(ge=0, le=9007199254740991)


class MessageView(BaseModel):
    id: UUID
    conversation_id: UUID
    sequence: int
    mine: bool
    client_message_id: UUID | None = None
    body: str | None
    created_at: datetime
    deleted_at: datetime | None


class ConversationView(BaseModel):
    id: UUID
    person: Person | None
    can_send: bool
    created_at: datetime
    last_message_at: datetime | None
    last_message: MessageView | None
    unread_count: int
    last_read_sequence: int
    peer_read_sequence: int
    latest_sequence: int


class ConversationList(BaseModel):
    items: list[ConversationView]
    next_cursor: UUID | None = None


class MessagePage(BaseModel):
    items: list[MessageView]
    next_before: int | None = None
    next_after: int | None = None


class MessageReportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: Literal[
        "harassment",
        "spam",
        "impersonation",
        "inappropriate_content",
        "suspicious_behavior",
        "other",
    ]
    description: str = Field(default="", max_length=1000)


class SocketInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["watch", "typing", "ping"]
    conversation_id: UUID | None = None
    active: bool = False
