"""Shared artwork is derived only from validated, persisted Steam metadata."""

import re
from typing import Literal

from pydantic import BaseModel


class GameVisual(BaseModel):
    icon_url: str | None = None
    thumbnail_url: str | None = None
    card_url: str | None = None
    source: Literal["steam", "unavailable"] = "unavailable"


def icon_hash(value: object) -> str | None:
    return (
        value.lower()
        if isinstance(value, str) and re.fullmatch(r"[a-fA-F0-9]{40}", value)
        else None
    )


def game_visual(app_id: int, value: object) -> GameVisual:
    hashed = icon_hash(value)
    if type(app_id) is not int or not 1 <= app_id <= 4294967295:
        return GameVisual()
    # Public Steam Library artwork is a presentation candidate, not an availability
    # claim. No provider request, user identity or persisted URL is required.
    assets = f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{app_id}"
    return GameVisual(
        icon_url=(
            f"https://media.steampowered.com/steamcommunity/public/images/apps/{app_id}/{hashed}.jpg"
            if hashed
            else None
        ),
        thumbnail_url=f"{assets}/header.jpg",
        card_url=f"{assets}/library_hero.jpg",
        source="steam",
    )
