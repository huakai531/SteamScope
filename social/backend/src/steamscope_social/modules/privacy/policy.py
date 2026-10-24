from typing import Literal
from uuid import UUID


def can_view(
    owner_id: UUID,
    actor_id: UUID | None,
    visibility: Literal["private", "connections", "public"],
    *,
    account_active: bool,
    source_available: bool,
) -> bool:
    """Phase 2 has no relationship source; connections-only always fails for non-owners."""
    if not account_active or not source_available:
        return False
    return actor_id == owner_id or visibility == "public"
