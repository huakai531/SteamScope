from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from steamscope_social.core.database import Base, utcnow


class User(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    handle: Mapped[str] = mapped_column(String(24))
    display_name: Mapped[str] = mapped_column(String(60))
    biography: Mapped[str] = mapped_column(String(500), default="")
    locale: Mapped[str] = mapped_column(String(16), default="en")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    status: Mapped[str] = mapped_column(String(16), default="active")
    avatar_key: Mapped[str | None] = mapped_column(String(37))
    avatar_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        Index("uq_users_handle_ci", func.lower(handle), unique=True),
        CheckConstraint("handle ~ '^[A-Za-z][A-Za-z0-9_]{2,23}$'", name="ck_users_handle"),
        CheckConstraint("status IN ('active','disabled','deleting')", name="ck_users_status"),
        CheckConstraint(
            "avatar_key IS NULL OR avatar_key ~ '^[a-f0-9]{32}\\.webp$'", name="ck_users_avatar_key"
        ),
    )


class AvatarDeletion(Base):
    """Transactional deletion outbox, retained until storage removal succeeds."""

    __tablename__ = "avatar_deletions"
    key: Mapped[str] = mapped_column(String(37), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        CheckConstraint("key ~ '^[a-f0-9]{32}\\.webp$'", name="ck_avatar_deletion_key"),
    )
