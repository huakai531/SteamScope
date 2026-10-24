"""Shared schema cache and personal snapshots, coordinated by the existing job fence."""

import hashlib
import json
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from steamscope_social.core.config import Settings
from steamscope_social.core.resources import Resources
from steamscope_social.modules.steam.client import Snapshot, SteamClient
from steamscope_social.modules.steam.models import (
    AchievementDefinition,
    AchievementSchema,
    AchievementState,
    SyncState,
    UserAchievement,
    UserGame,
)

if TYPE_CHECKING:
    from steamscope_social.modules.steam.jobs import Claim


async def eligible(db: AsyncSession, owner: UUID, app_id: int) -> bool:
    state = await db.get(SyncState, (owner, "library"))
    return bool(
        state and state.exposed and state.snapshot_id and await db.get(UserGame, (owner, app_id))
    )


def schema_fresh(schema: AchievementSchema, now: datetime, settings: Settings) -> bool:
    return bool(
        schema.revision
        and schema.last_success_at
        and schema.status in {"populated", "empty"}
        and schema.last_success_at + timedelta(seconds=settings.steam_schema_ttl_seconds) > now
    )


async def schema_for_claim(
    resources: Resources, settings: Settings, client: SteamClient, claim: "Claim"
) -> Snapshot | None:
    from steamscope_social.modules.steam.jobs import budget, database_now, fenced, record_outcome

    async with resources.sessions() as db, db.begin():
        current = await fenced(db, claim)
        if current is None:
            return None
        job, _ = current
        now = await database_now(db)
        await db.execute(
            insert(AchievementSchema)
            .values(app_id=claim.app_id, language="english", status="never", code="NEVER_SYNCED")
            .on_conflict_do_nothing()
        )
        row = await db.scalar(
            select(AchievementSchema)
            .where(
                AchievementSchema.app_id == claim.app_id, AchievementSchema.language == "english"
            )
            .with_for_update()
        )
        assert row is not None
        cached = None
        if schema_fresh(row, now, settings):
            cached = Snapshot(row.status, "SCHEMA_CACHE_HIT", schema_revision=row.revision)
        elif row.lease_token and row.lease_until and row.lease_until > now:
            cached = Snapshot(
                "retry",
                "SCHEMA_REFRESH_BUSY",
                max(1, int((row.lease_until - now).total_seconds()) + 1),
            )
        elif row.retry_at and row.retry_at > now:
            cached = Snapshot(
                "retry", "SCHEMA_RETRY_WAIT", max(1, int((row.retry_at - now).total_seconds()) + 1)
            )
        if cached is not None:
            await record_outcome(db, claim, job, "schema", cached)
            return cached
        delay = await budget(db, claim.user_id, settings)
        if delay:
            limited = Snapshot("retry", "APPLICATION_RATE_LIMIT", delay)
            await record_outcome(db, claim, job, "schema", limited)
            return limited
        row.lease_token, row.lease_until = claim.token, now + timedelta(seconds=30)
        row.last_attempt_at = now

    # Both user/job and cache transactions are closed before HTTP.
    result = await client.fetch("schema", claim.steam_id, claim.app_id)
    async with resources.sessions() as db, db.begin():
        current = await fenced(db, claim)
        if current is None:
            return None
        job, _ = current
        row = await db.scalar(
            select(AchievementSchema)
            .where(
                AchievementSchema.app_id == claim.app_id, AchievementSchema.language == "english"
            )
            .with_for_update()
        )
        now = await database_now(db)
        if (
            row is None
            or row.lease_token != claim.token
            or row.lease_until is None
            or row.lease_until <= now
        ):
            await record_outcome(
                db, claim, job, "schema", Snapshot("retry", "SCHEMA_LEASE_EXPIRED", 1)
            )
            return Snapshot("retry", "SCHEMA_LEASE_EXPIRED", 1)
        row.status, row.code = result.status, result.code
        row.lease_token, row.lease_until = None, None
        if result.status in {"populated", "empty"}:
            ordered = sorted(result.definitions, key=lambda d: d.api_name)
            revision = hashlib.sha256(
                json.dumps(
                    [asdict(d) for d in ordered], sort_keys=True, ensure_ascii=False
                ).encode()
            ).hexdigest()
            await db.execute(
                delete(AchievementDefinition).where(
                    AchievementDefinition.app_id == claim.app_id,
                    AchievementDefinition.language == "english",
                )
            )
            for start in range(0, len(ordered), 250):
                await db.execute(
                    insert(AchievementDefinition).values(
                        [
                            {"app_id": claim.app_id, "language": "english", **asdict(d)}
                            for d in ordered[start : start + 250]
                        ]
                    )
                )
            row.revision, row.last_success_at, row.retry_at = revision, now, None
            result = replace(result, schema_revision=revision)
        else:
            # Failed refresh cannot erase definitions or move the last success time.
            row.retry_at = now + timedelta(seconds=max(60, result.retry_after))
        await record_outcome(db, claim, job, "schema", result)
        await db.flush()
        if job.lease_until is None or job.lease_until <= await database_now(db):
            await db.rollback()
            return None
        return result


async def persist_achievements(
    db: AsyncSession,
    owner: UUID,
    app_id: int,
    state: AchievementState,
    result: Snapshot,
    now: datetime,
) -> Snapshot:
    if result.status not in {"populated", "empty"}:
        return result
    schema = await db.scalar(
        select(AchievementSchema)
        .where(AchievementSchema.app_id == app_id, AchievementSchema.language == "english")
        .with_for_update()
    )
    definitions = set(
        await db.scalars(
            select(AchievementDefinition.api_name).where(
                AchievementDefinition.app_id == app_id, AchievementDefinition.language == "english"
            )
        )
    )
    complete = bool(
        schema
        and result.schema_revision
        and schema.revision == result.schema_revision
        and schema.status in {"populated", "empty"}
        and definitions == {a.api_name for a in result.achievements}
        and all(a.unlocked is not None for a in result.achievements)
    )
    if not complete and state.snapshot_id is not None:
        # A partial observation cannot destructively replace an accepted snapshot.
        # Keep its rows/revision/success time, but hide progress until valid recovery.
        return replace(result, status="unknown", code="SCHEMA_PLAYER_MISMATCH")
    await db.execute(
        delete(UserAchievement).where(
            UserAchievement.user_id == owner, UserAchievement.app_id == app_id
        )
    )
    for start in range(0, len(result.achievements), 250):
        await db.execute(
            insert(UserAchievement).values(
                [
                    {"user_id": owner, "app_id": app_id, "observed_at": now, **asdict(a)}
                    for a in result.achievements[start : start + 250]
                ]
            )
        )
    state.schema_revision = result.schema_revision
    return result if complete else replace(result, status="partial", code="SCHEMA_PLAYER_MISMATCH")
