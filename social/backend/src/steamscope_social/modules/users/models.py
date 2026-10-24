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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        Index("uq_users_handle_ci", func.lower(handle), unique=True),
        CheckConstraint("handle ~ '^[A-Za-z][A-Za-z0-9_]{2,23}$'", name="ck_users_handle"),
        CheckConstraint("status IN ('active','disabled','deleting')", name="ck_users_status"),
    )
