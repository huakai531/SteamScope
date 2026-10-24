from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from steamscope_social.core.database import Base, utcnow


class ConnectionRequest(Base):
    __tablename__ = "connection_requests"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    sender_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    receiver_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    user_id_low: Mapped[UUID] = mapped_column()
    user_id_high: Mapped[UUID] = mapped_column()
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("sender_id <> receiver_id", name="ck_request_no_self"),
        CheckConstraint(
            "user_id_low = least(sender_id,receiver_id) AND "
            "user_id_high = greatest(sender_id,receiver_id)",
            name="ck_request_pair",
        ),
        CheckConstraint(
            "status IN ('pending','accepted','rejected','cancelled','expired')",
            name="ck_request_status",
        ),
        Index(
            "uq_request_pending_pair",
            "user_id_low",
            "user_id_high",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_request_sender", "sender_id", "status", "created_at"),
        Index("ix_request_receiver", "receiver_id", "status", "created_at"),
    )


class Connection(Base):
    __tablename__ = "connections"
    user_id_low: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    user_id_high: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        CheckConstraint("user_id_low < user_id_high", name="ck_connection_order"),
        Index("ix_connection_high", "user_id_high"),
    )


class UserBlock(Base):
    __tablename__ = "user_blocks"
    blocker_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    blocked_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        CheckConstraint("blocker_id <> blocked_id", name="ck_block_no_self"),
        Index("ix_block_target", "blocked_id"),
    )


class UserReport(Base):
    __tablename__ = "user_reports"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    reporter_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    target_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reason: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(String(1000), default="")
    status: Mapped[str] = mapped_column(String(16), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("reporter_id <> target_id", name="ck_report_no_self"),
        CheckConstraint(
            "reason IN ('harassment','spam','impersonation','inappropriate_content',"
            "'suspicious_behavior','other')",
            name="ck_report_reason",
        ),
        CheckConstraint("status IN ('open','reviewed','closed')", name="ck_report_status"),
        Index("ix_report_reporter", "reporter_id", "created_at"),
        Index("ix_report_target", "target_id", "status"),
        Index("ix_report_expiry", "expires_at"),
    )


class SocialNotification(Base):
    __tablename__ = "social_notifications"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    recipient_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    request_id: Mapped[UUID] = mapped_column(
        ForeignKey("connection_requests.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "kind IN ('connection_request_received','connection_request_accepted')",
            name="ck_notification_kind",
        ),
        CheckConstraint("recipient_id <> actor_id", name="ck_notification_actor"),
        Index("uq_notification_event", "recipient_id", "request_id", "kind", unique=True),
        Index("ix_notification_inbox", "recipient_id", "read_at", "created_at"),
    )
