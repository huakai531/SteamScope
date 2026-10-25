from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

LOCALES = {"en", "en-US", "zh-CN", "zh-TW", "ja", "ko", "de", "fr", "es", "pt-BR"}


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    handle: str | None = Field(
        default=None, min_length=3, max_length=24, pattern=r"^[A-Za-z][A-Za-z0-9_]+$"
    )
    display_name: str | None = Field(default=None, min_length=1, max_length=60)
    biography: str | None = Field(default=None, max_length=500)
    locale: str | None = None
    timezone: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def no_nulls(self) -> "ProfileUpdate":
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Fields cannot be null")
        return self

    @field_validator("display_name", "biography")
    @classmethod
    def plain_text(cls, value: str | None) -> str | None:
        if value is not None and (
            any(ord(c) < 32 and c not in "\n\t" for c in value) or not value.strip() and value != ""
        ):
            raise ValueError("Use plain text without control characters")
        return value

    @field_validator("locale")
    @classmethod
    def valid_locale(cls, value: str | None) -> str | None:
        if value is not None and value not in LOCALES:
            raise ValueError("Select a supported locale")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError):
                raise ValueError("Use a valid IANA timezone") from None
        return value


class AccountView(BaseModel):
    avatar_url: str | None = None
    id: UUID
    handle: str
    display_name: str
    biography: str
    locale: str
    timezone: str
    steam_id: str
    created_at: datetime
    steam_identity_verified: Literal[True] = True
    steam_data_synchronized: bool = False


class DeleteAccount(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: Literal["DELETE"]
