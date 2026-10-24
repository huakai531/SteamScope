"""PostgreSQL queue. Lock order: user -> job/link -> shared budget.

Every persistence path fences under the same user lock as account deletion/clearing.
No transaction, connection or lock is retained during an upstream request.
"""

import asyncio
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from steamscope_social.core.config import Settings
from steamscope_social.core.resources import Resources
from steamscope_social.modules.auth.models import SteamAccount
from steamscope_social.modules.auth.security import AuthError
from steamscope_social.modules.steam.client import (
    RESOURCES,
    Resource,
    Snapshot,
    SteamClient,
    capability,
)
from steamscope_social.modules.steam.models import (
    AchievementSchema,
    AchievementState,
    Game,
    RecentGame,
    RequestBudget,
    SteamFriend,
    SyncJob,
    SyncRun,
    SyncState,
    UserAchievement,
    UserGame,
)
from steamscope_social.modules.steam.repository import (
    eligible,
    persist_achievements,
    schema_for_claim,
)
from steamscope_social.modules.users.models import User

ACTIVE = ("queued", "running", "retry")
SUCCESS = ("populated", "empty")


async def database_now(db: AsyncSession) -> datetime:
    value = await db.scalar(select(func.clock_timestamp()))
    assert isinstance(value, datetime)
    return value


async def enqueue(
    db: AsyncSession, user: User, settings: Settings, scope: str = "base", app_id: int = 0
) -> tuple[SyncJob, bool]:
    """Caller holds the user lock; one active job per scope/app, at most five per owner."""
    if capability(settings) != "configured":
        raise AuthError(503, "STEAM_SYNC_NOT_CONFIGURED")
    if scope not in {"base", "achievements", "friends"} or (
        scope != "achievements" and app_id != 0
    ):
        raise AuthError(422, "INVALID_REQUEST")
    if scope == "achievements" and not await eligible(db, user.id, app_id):
        raise AuthError(404, "STEAM_GAME_NOT_ELIGIBLE")
    active = await db.scalar(
        select(SyncJob).where(
            SyncJob.user_id == user.id,
            SyncJob.scope == scope,
            SyncJob.app_id == app_id,
            SyncJob.status.in_(ACTIVE),
        )
    )
    if active:
        return active, True
    if (
        await db.scalar(
            select(func.count())
            .select_from(SyncJob)
            .where(SyncJob.user_id == user.id, SyncJob.status.in_(ACTIVE))
        )
        or 0
    ) >= 5:
        raise AuthError(429, "STEAM_QUEUE_LIMIT")
    now = await database_now(db)
    latest = await db.scalar(
        select(SyncJob)
        .where(SyncJob.user_id == user.id, SyncJob.scope == scope, SyncJob.app_id == app_id)
        .order_by(SyncJob.created_at.desc())
        .limit(1)
    )
    if latest and latest.created_at + timedelta(seconds=settings.steam_sync_cooldown_seconds) > now:
        raise AuthError(429, "STEAM_SYNC_COOLDOWN")
    link = await db.scalar(select(SteamAccount).where(SteamAccount.user_id == user.id))
    if link is None:
        raise AuthError(403, "ACCOUNT_UNAVAILABLE")
    # Keep at most 20 finished histories per owner plus the new active job.
    older = (
        select(SyncJob.id)
        .where(SyncJob.user_id == user.id, SyncJob.status.not_in(ACTIVE))
        .order_by(SyncJob.created_at.desc())
        .offset(19)
    )
    await db.execute(delete(SyncJob).where(SyncJob.id.in_(older)))
    job = SyncJob(
        user_id=user.id,
        link_id=link.id,
        generation=link.import_generation,
        scope=scope,
        app_id=app_id,
        created_at=now,
        available_at=now,
    )
    db.add(job)
    await db.flush()
    return job, False


@dataclass(frozen=True)
class Claim:
    job_id: UUID
    user_id: UUID
    link_id: UUID
    generation: int
    token: UUID
    steam_id: str
    attempts: int
    scope: str = "base"
    app_id: int = 0


async def fenced(db: AsyncSession, claim: Claim) -> tuple[SyncJob, SteamAccount] | None:
    user = await db.scalar(select(User).where(User.id == claim.user_id).with_for_update())
    if user is None or user.status != "active":
        return None
    job = await db.scalar(select(SyncJob).where(SyncJob.id == claim.job_id).with_for_update())
    link = await db.get(SteamAccount, claim.link_id)
    now = await database_now(db)
    if (
        job is None
        or link is None
        or link.user_id != user.id
        or job.user_id != claim.user_id
        or job.link_id != claim.link_id
        or link.steam_id != claim.steam_id
        or link.import_generation != claim.generation
        or job.generation != claim.generation
        or job.scope != claim.scope
        or job.app_id != claim.app_id
        or job.status != "running"
        or job.claim_token != claim.token
        or job.lease_until is None
        or job.lease_until <= now
    ):
        return None
    if claim.scope == "achievements" and not await eligible(db, claim.user_id, claim.app_id):
        return None
    return job, link


def scoped_resources(scope: str) -> tuple[Resource, ...]:
    return (
        ("schema", "achievements")
        if scope == "achievements"
        else ("friends",)
        if scope == "friends"
        else RESOURCES
    )


def terminal(outcomes: dict[str, str], scope: str = "base") -> str:
    expected = scoped_resources(scope)
    good = sum(outcomes.get(r) in SUCCESS for r in expected)
    return (
        "succeeded"
        if good == len(expected)
        else "partial"
        if good or "partial" in outcomes.values()
        else "failed"
    )


async def claim_next(resources: Resources, settings: Settings) -> Claim | None:
    async with resources.sessions() as db, db.begin():
        now = await database_now(db)
        candidates = (
            await db.execute(
                select(SyncJob.id, SyncJob.user_id)
                .where(
                    or_(
                        (SyncJob.status.in_(("queued", "retry"))) & (SyncJob.available_at <= now),
                        (SyncJob.status == "running") & (SyncJob.lease_until <= now),
                    )
                )
                .order_by(SyncJob.created_at, SyncJob.id)
                .limit(32)
            )
        ).all()
        for job_id, user_id in candidates:
            user = await db.scalar(
                select(User).where(User.id == user_id).with_for_update(skip_locked=True)
            )
            if user is None:
                continue
            job = await db.scalar(
                select(SyncJob).where(SyncJob.id == job_id).with_for_update(skip_locked=True)
            )
            if (
                job is None
                or job.status not in ACTIVE
                or (job.status == "running" and job.lease_until and job.lease_until > now)
                or job.available_at > now
            ):
                continue
            link = await db.get(SteamAccount, job.link_id)
            if (
                user.status != "active"
                or link is None
                or link.import_generation != job.generation
                or (job.scope == "achievements" and not await eligible(db, user.id, job.app_id))
            ):
                job.status, job.finished_at, job.claim_token = "cancelled", now, None
                continue
            if job.claim_token:
                await db.execute(
                    update(SyncRun)
                    .where(SyncRun.claim_token == job.claim_token, SyncRun.finished_at.is_(None))
                    .values(status="lease_expired", finished_at=now)
                )
            if job.attempts >= settings.steam_sync_max_attempts:
                job.status, job.finished_at, job.claim_token = (
                    terminal(job.outcomes, job.scope),
                    now,
                    None,
                )
                continue
            job.attempts += 1
            job.status, job.claim_token = "running", uuid4()
            job.lease_until = now + timedelta(seconds=settings.steam_sync_lease_seconds)
            db.add(
                SyncRun(
                    job_id=job.id, claim_token=job.claim_token, attempt=job.attempts, started_at=now
                )
            )
            return Claim(
                job.id,
                user.id,
                link.id,
                job.generation,
                job.claim_token,
                link.steam_id,
                job.attempts,
                job.scope,
                job.app_id,
            )
    return None


async def budget(db: AsyncSession, user_id: UUID, settings: Settings) -> int:
    """Atomically reserve actual calls, including failed calls; never refunds on crash."""
    now = await database_now(db)
    specs = [
        ("day", "shared", 86400, settings.steam_requests_per_day),
        ("minute", "shared", 60, settings.steam_requests_per_minute),
        ("user", str(user_id), 3600, settings.steam_user_requests_per_hour),
    ]
    rows = []
    delay = 0
    for scope, owner, seconds, limit in specs:
        start = datetime.fromtimestamp(int(now.timestamp()) // seconds * seconds, tz=now.tzinfo)
        await db.execute(
            insert(RequestBudget)
            .values(scope=scope, owner=owner, window_start=start, used=0)
            .on_conflict_do_nothing()
        )
        row = await db.scalar(
            select(RequestBudget)
            .where(RequestBudget.scope == scope, RequestBudget.owner == owner)
            .with_for_update()
        )
        assert row is not None
        if row.window_start < start:
            row.window_start, row.used = start, 0
        if row.blocked_until and row.blocked_until > now:
            delay = max(delay, int((row.blocked_until - now).total_seconds()) + 1)
        if row.used >= limit:
            delay = max(delay, int((start + timedelta(seconds=seconds) - now).total_seconds()) + 1)
        rows.append(row)
    if not delay:
        for row in rows:
            row.used += 1
    return delay


async def begin_resource(
    resources: Resources, settings: Settings, claim: Claim, resource: Resource
) -> int | None:
    async with resources.sessions() as db, db.begin():
        current = await fenced(db, claim)
        if current is None:
            return None
        job, _ = current
        if resource in job.outcomes and job.outcomes[resource] not in {"retry", "partial"}:
            return None
        delay = await budget(db, claim.user_id, settings)
        now = await database_now(db)
        state = await state_for(db, claim, resource)
        state.last_attempt_at = now
        return delay


async def state_for(
    db: AsyncSession, claim: Claim, resource: Resource
) -> SyncState | AchievementState:
    if resource == "achievements":
        row = await db.get(AchievementState, (claim.user_id, claim.app_id))
        if row is None:
            row = AchievementState(user_id=claim.user_id, app_id=claim.app_id)
            db.add(row)
        return row
    state = await db.get(SyncState, (claim.user_id, resource))
    if state is None:
        state = SyncState(user_id=claim.user_id, resource=resource)
        db.add(state)
    return state


async def record_outcome(
    db: AsyncSession, claim: Claim, job: SyncJob, resource: Resource, result: Snapshot
) -> None:
    now = await database_now(db)
    if result.code == "UPSTREAM_RATE_LIMIT":
        row = await db.scalar(
            select(RequestBudget)
            .where(RequestBudget.scope == "day", RequestBudget.owner == "shared")
            .with_for_update()
        )
        assert row is not None
        deadline = now + timedelta(seconds=result.retry_after)
        row.blocked_until = max(row.blocked_until or deadline, deadline)
    job.outcomes = {**job.outcomes, resource: result.status}
    run = await db.scalar(select(SyncRun).where(SyncRun.claim_token == claim.token))
    assert run is not None
    run.outcomes = {
        **run.outcomes,
        resource: result.status + ":" + result.code,
        **{resource + "." + key: value for key, value in result.diagnostics},
    }


async def save_resource(
    resources: Resources, claim: Claim, resource: Resource, result: Snapshot
) -> bool:
    async with resources.sessions() as db, db.begin():
        current = await fenced(db, claim)
        if current is None:
            return False
        job, link = current
        if resource in job.outcomes and job.outcomes[resource] not in {"retry", "partial"}:
            return False
        now = await database_now(db)
        state = await state_for(db, claim, resource)
        if resource == "achievements":
            assert isinstance(state, AchievementState)
            result = await persist_achievements(db, claim.user_id, claim.app_id, state, result, now)
        state.status, state.code = result.status, result.code
        if result.status in (*SUCCESS, "partial"):
            state.exposed = True
        elif result.status in {"restricted", "unknown", "unavailable"}:
            state.exposed = False
        if result.status in (*SUCCESS, "partial") or result.status == "restricted":
            if resource == "achievements":
                pass  # Validated player snapshot was persisted above, without definition FKs.
            elif resource == "friends":
                await db.execute(delete(SteamFriend).where(SteamFriend.user_id == claim.user_id))
                for start in range(0, len(result.friends), 500):
                    await db.execute(
                        insert(SteamFriend).values(
                            [
                                {
                                    "user_id": claim.user_id,
                                    "friend_steam_id64": f.steam_id,
                                    "friend_since": f.since,
                                    "observed_at": now,
                                }
                                for f in result.friends[start : start + 500]
                            ]
                        )
                    )
            elif resource == "profile":
                link.persona_name, link.profile_url = result.persona, result.profile_url
                link.avatar_url, link.source_visibility = result.avatar_url, result.visibility
            else:
                table = UserGame if resource == "library" else RecentGame
                # Entire response was validated before any destructive reconciliation.
                await db.execute(delete(table).where(table.user_id == claim.user_id))
                ordered = sorted(result.games, key=lambda g: g.app_id)
                for start in range(0, len(ordered), 500):
                    chunk = ordered[start : start + 500]
                    stmt = insert(Game).values(
                        [
                            {"app_id": g.app_id, "name": g.name, "icon_hash": g.icon_hash}
                            for g in chunk
                        ]
                    )
                    await db.execute(
                        stmt.on_conflict_do_update(
                            index_elements=[Game.app_id],
                            set_={
                                "name": func.coalesce(stmt.excluded.name, Game.name),
                                "icon_hash": func.coalesce(stmt.excluded.icon_hash, Game.icon_hash),
                            },
                        )
                    )
                    rows = [
                        {
                            "user_id": claim.user_id,
                            "app_id": g.app_id,
                            "total_minutes": g.total_minutes,
                            "recent_minutes": g.recent_minutes,
                            "observed_at": now,
                            **(
                                {"last_played_at": g.last_played_at}
                                if resource == "library"
                                else {}
                            ),
                        }
                        for g in chunk
                    ]
                    await db.execute(insert(table).values(rows))
            if result.status in (*SUCCESS, "partial"):
                state.last_success_at, state.snapshot_id = now, uuid4()
            else:
                state.snapshot_id = None
        # Ambiguous/denied responses hide old data at read time, but never erase it.
        await record_outcome(db, claim, job, resource, result)
        await db.flush()
        if job.lease_until is None or job.lease_until <= await database_now(db):
            await db.rollback()
            return False
        return True


async def finish(
    resources: Resources,
    settings: Settings,
    claim: Claim,
    delay: int = 0,
    *,
    interrupted: bool = False,
) -> bool:
    async with resources.sessions() as db, db.begin():
        current = await fenced(db, claim)
        if current is None:
            return False
        job, _ = current
        now = await database_now(db)
        retry = interrupted or any(
            job.outcomes.get(r) in {None, "retry"} for r in scoped_resources(job.scope)
        )
        job.status = (
            "retry"
            if retry and job.attempts < settings.steam_sync_max_attempts
            else terminal(job.outcomes, job.scope)
        )
        job.available_at = now + timedelta(
            seconds=max(delay, min(300, 5 * 2**job.attempts) + random.uniform(0, 3))
        )
        job.finished_at = None if job.status == "retry" else now
        job.claim_token, job.lease_until = None, None
        run = await db.scalar(select(SyncRun).where(SyncRun.claim_token == claim.token))
        assert run is not None
        run.finished_at, run.status = now, "interrupted" if interrupted else job.status
        return True


async def process_claim(
    resources: Resources, settings: Settings, client: SteamClient, claim: Claim
) -> None:
    delay = 0
    try:
        revision = None
        if claim.scope == "achievements":
            schema = await schema_for_claim(resources, settings, client, claim)
            if schema is None:
                return
            revision, delay = schema.schema_revision, schema.retry_after
            if schema.code in {
                "SCHEMA_REFRESH_BUSY",
                "SCHEMA_RETRY_WAIT",
                "SCHEMA_LEASE_EXPIRED",
                "APPLICATION_RATE_LIMIT",
            }:
                await finish(resources, settings, claim, delay)
                return
        for resource in scoped_resources(claim.scope):
            if resource == "schema":
                continue
            limited = await begin_resource(resources, settings, claim, resource)
            if limited is None:
                continue
            result = (
                Snapshot("retry", "APPLICATION_RATE_LIMIT", limited)
                if limited
                else await client.fetch(resource, claim.steam_id, claim.app_id)
            )
            if resource == "achievements":
                from dataclasses import replace

                result = replace(result, schema_revision=revision)
            delay = max(delay, result.retry_after)
            if not await save_resource(resources, claim, resource, result):
                return
        await finish(resources, settings, claim, delay)
    except asyncio.CancelledError:
        await finish(resources, settings, claim, interrupted=True)
        raise


async def clear_imported(db: AsyncSession, user: User, *, deleting: bool = False) -> None:
    """Authenticated caller holds user lock; all workers acquire this same lock first."""
    link = await db.scalar(select(SteamAccount).where(SteamAccount.user_id == user.id))
    if link:
        link.import_generation += 1
        link.persona_name = link.profile_url = link.avatar_url = None
        link.source_visibility = None
    now = await database_now(db)
    ids = select(SyncJob.id).where(SyncJob.user_id == user.id)
    await db.execute(
        update(SyncRun)
        .where(SyncRun.job_id.in_(ids), SyncRun.finished_at.is_(None))
        .values(status="cancelled", finished_at=now)
    )
    await db.execute(
        update(SyncJob)
        .where(SyncJob.user_id == user.id, SyncJob.status.in_(ACTIVE))
        .values(status="cancelled", claim_token=None, lease_until=None, finished_at=now)
    )
    for table in (UserGame, RecentGame, SyncState, UserAchievement, AchievementState, SteamFriend):
        await db.execute(delete(table).where(table.user_id == user.id))
    # New scoped history includes a selected app; erase that personal association on clear.
    await db.execute(
        update(AchievementSchema)
        .where(
            AchievementSchema.lease_token.in_(
                select(SyncRun.claim_token).where(SyncRun.job_id.in_(ids))
            )
        )
        .values(lease_token=None, lease_until=None)
    )
    await db.execute(delete(SyncJob).where(SyncJob.user_id == user.id, SyncJob.scope != "base"))
    if deleting:
        user.status = "deleting"
        await db.execute(
            delete(RequestBudget).where(
                RequestBudget.scope == "user", RequestBudget.owner == str(user.id)
            )
        )
    # No imported-data Redis cache exists; shared catalog contains no owner association.
