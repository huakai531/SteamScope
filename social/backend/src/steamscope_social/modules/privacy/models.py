from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from steamscope_social.core.database import Base


class PrivacySettings(Base):
    __tablename__ = "privacy_settings"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    profile: Mapped[str] = mapped_column(String(16), default="private")
    library: Mapped[str] = mapped_column(String(16), default="private")
    playtime: Mapped[str] = mapped_column(String(16), default="private")
    achievements: Mapped[str] = mapped_column(String(16), default="private")
    presence: Mapped[str] = mapped_column(String(16), default="private")
    discovery: Mapped[bool] = mapped_column(Boolean, default=False)
    connection_requests: Mapped[str] = mapped_column(String(16), default="nobody")
    messaging: Mapped[str] = mapped_column(String(16), default="nobody")
    __table_args__ = tuple(
        CheckConstraint(
            f"{field} IN ('private','connections','public')", name=f"ck_privacy_{field}"
        )
        for field in ("profile", "library", "playtime", "achievements", "presence")
    ) + (
        CheckConstraint(
            "connection_requests IN ('nobody','discoverable')", name="ck_privacy_requests"
        ),
        CheckConstraint("messaging IN ('nobody','connections')", name="ck_privacy_messaging"),
    )
