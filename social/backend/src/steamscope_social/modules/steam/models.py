from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from steamscope_social.core.database import Base, utcnow


class Game(Base):
    __tablename__ = "games"
    app_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(256))
    icon_hash: Mapped[str | None] = mapped_column(String(40))
    __table_args__ = (CheckConstraint("app_id > 0 AND app_id <= 4294967295", name="ck_games_app"),)


class UserGame(Base):
    __tablename__ = "user_games"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    app_id: Mapped[int] = mapped_column(ForeignKey("games.app_id"), primary_key=True)
    total_minutes: Mapped[int | None]
    recent_minutes: Mapped[int | None]
    last_played_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("total_minutes >= 0 AND recent_minutes >= 0", name="ck_user_games_minutes"),
    )


class RecentGame(Base):
    __tablename__ = "steam_recent_games"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    app_id: Mapped[int] = mapped_column(ForeignKey("games.app_id"), primary_key=True)
    total_minutes: Mapped[int | None]
    recent_minutes: Mapped[int | None]
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "total_minutes >= 0 AND recent_minutes >= 0", name="ck_recent_games_minutes"
        ),
    )


class SyncState(Base):
    __tablename__ = "steam_resource_states"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    resource: Mapped[str] = mapped_column(String(16), primary_key=True)
    status: Mapped[str] = mapped_column(String(24), default="never")
    code: Mapped[str] = mapped_column(String(64), default="NEVER_SYNCED")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snapshot_id: Mapped[UUID | None]
    exposed: Mapped[bool] = mapped_column(default=False)
    __table_args__ = (
        CheckConstraint(
            "resource IN ('profile','library','recent','friends')", name="ck_sync_resource"
        ),
    )


class SyncJob(Base):
    __tablename__ = "steam_sync_jobs"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    link_id: Mapped[UUID] = mapped_column(ForeignKey("steam_accounts.id", ondelete="CASCADE"))
    generation: Mapped[int]
    scope: Mapped[str] = mapped_column(String(16), default="base", server_default="base")
    app_id: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(16), default="queued")
    attempts: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_token: Mapped[UUID | None]
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcomes: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    __table_args__ = (
        CheckConstraint(
            "(scope IN ('base','friends') AND app_id = 0) OR "
            "(scope = 'achievements' AND app_id > 0 AND app_id <= 4294967295)",
            name="ck_sync_job_scope",
        ),
        CheckConstraint(
            "status IN ('queued','running','retry','succeeded','partial','failed','cancelled')",
            name="ck_sync_job_status",
        ),
        CheckConstraint("attempts >= 0 AND generation >= 0", name="ck_sync_job_counters"),
        Index(
            "uq_sync_active_scope",
            "user_id",
            "scope",
            "app_id",
            unique=True,
            postgresql_where=text("status IN ('queued','running','retry')"),
        ),
        Index("ix_sync_claim", "status", "available_at", "created_at"),
    )


class SyncRun(Base):
    __tablename__ = "steam_sync_runs"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("steam_sync_jobs.id", ondelete="CASCADE"), index=True
    )
    claim_token: Mapped[UUID] = mapped_column(unique=True)
    attempt: Mapped[int]
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default="running")
    outcomes: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)


class RequestBudget(Base):
    """Conservative single configured key budget; survives restart and covers all workers."""

    __tablename__ = "steam_request_budgets"
    scope: Mapped[str] = mapped_column(String(16), primary_key=True)
    owner: Mapped[str] = mapped_column(String(36), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[int] = mapped_column(default=0)
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AchievementSchema(Base):
    """Shared app/language snapshot and bounded refresh lease; contains no user identity."""

    __tablename__ = "steam_achievement_schemas"
    app_id: Mapped[int] = mapped_column(ForeignKey("games.app_id"), primary_key=True)
    language: Mapped[str] = mapped_column(String(16), primary_key=True, default="english")
    status: Mapped[str] = mapped_column(String(24), default="never")
    code: Mapped[str] = mapped_column(String(64), default="NEVER_SYNCED")
    revision: Mapped[str | None] = mapped_column(String(64))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("language = 'english'", name="ck_schema_language"),)


class AchievementDefinition(Base):
    __tablename__ = "steam_achievement_definitions"
    app_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    language: Mapped[str] = mapped_column(String(16), primary_key=True)
    api_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(256))
    description: Mapped[str | None] = mapped_column(String(2048))
    hidden: Mapped[bool]
    icon_url: Mapped[str | None] = mapped_column(String(512))
    icon_gray_url: Mapped[str | None] = mapped_column(String(512))
    __table_args__ = (
        ForeignKeyConstraint(
            ["app_id", "language"],
            ["steam_achievement_schemas.app_id", "steam_achievement_schemas.language"],
            ondelete="CASCADE",
        ),
    )


class AchievementState(Base):
    __tablename__ = "steam_achievement_states"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    app_id: Mapped[int] = mapped_column(ForeignKey("games.app_id"), primary_key=True)
    status: Mapped[str] = mapped_column(String(24), default="never")
    code: Mapped[str] = mapped_column(String(64), default="NEVER_SYNCED")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snapshot_id: Mapped[UUID | None]
    exposed: Mapped[bool] = mapped_column(default=False)
    schema_revision: Mapped[str | None] = mapped_column(String(64))
    language: Mapped[str] = mapped_column(String(16), default="english")
    __table_args__ = (CheckConstraint("language = 'english'", name="ck_player_language"),)


class UserAchievement(Base):
    """No FK to definitions: schema replacement cannot erase or cascade player evidence."""

    __tablename__ = "steam_user_achievements"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    app_id: Mapped[int] = mapped_column(ForeignKey("games.app_id"), primary_key=True)
    api_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    unlocked: Mapped[bool | None]
    unlocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SteamFriend(Base):
    __tablename__ = "steam_friends"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    friend_steam_id64: Mapped[str] = mapped_column(String(17), primary_key=True)
    friend_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "friend_steam_id64 ~ '^[0-9]{17}$' AND "
            "friend_steam_id64 BETWEEN '76561197960265728' AND '76561202255233023'",
            name="ck_friend_steam_id",
        ),
    )
