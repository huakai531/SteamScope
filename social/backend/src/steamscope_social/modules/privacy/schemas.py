from typing import Literal

from pydantic import BaseModel, ConfigDict

Visibility = Literal["private", "connections", "public"]


class PrivacyView(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, strict=True)
    profile: Visibility = "private"
    library: Visibility = "private"
    playtime: Visibility = "private"
    achievements: Visibility = "private"
    presence: Visibility = "private"
    discovery: bool = False
    connection_requests: Literal["nobody", "discoverable"] = "nobody"
    messaging: Literal["nobody", "connections"] = "nobody"
