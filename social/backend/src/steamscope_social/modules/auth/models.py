from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from steamscope_social.core.database import Base, utcnow


class SteamAccount(Base):
    __tablename__ = "steam_accounts"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    steam_id: Mapped[str] = mapped_column(String(20), unique=True)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    import_generation: Mapped[int] = mapped_column(default=0, server_default="0")
    persona_name: Mapped[str | None] = mapped_column(String(128))
    profile_url: Mapped[str | None] = mapped_column(String(256))
    avatar_url: Mapped[str | None] = mapped_column(String(512))
    source_visibility: Mapped[int | None]
    __table_args__ = (CheckConstraint("steam_id ~ '^[0-9]{17}$'", name="ck_steam_accounts_id"),)


class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    authenticated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("expires_at > created_at", name="ck_sessions_expiry"),)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    state_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    browser_digest: Mapped[str] = mapped_column(String(64))
    purpose: Mapped[str] = mapped_column(String(12))
    destination: Mapped[str] = mapped_column(String(64))
    bound_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    bound_session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("user_sessions.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    __table_args__ = (
        CheckConstraint("purpose IN ('login','reauth')", name="ck_login_attempt_purpose"),
        CheckConstraint("expires_at > created_at", name="ck_login_attempt_expiry"),
        CheckConstraint(
            "purpose != 'reauth' OR (bound_user_id IS NOT NULL AND bound_session_id IS NOT NULL)",
            name="ck_login_attempt_binding",
        ),
    )
