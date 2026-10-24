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
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from steamscope_social.core.database import Base, utcnow


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id_low: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    user_id_high: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_sequence: Mapped[int] = mapped_column(BigInteger, default=1)
    __table_args__ = (
        UniqueConstraint("user_id_low", "user_id_high", name="uq_direct_pair"),
        CheckConstraint("user_id_low < user_id_high", name="ck_direct_order"),
        CheckConstraint("next_sequence > 0", name="ck_direct_sequence"),
        Index("ix_conversation_high", "user_id_high"),
    )


class ConversationMember(Base):
    __tablename__ = "conversation_members"
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_read_sequence: Mapped[int] = mapped_column(BigInteger, default=0)
    __table_args__ = (
        CheckConstraint("last_read_sequence >= 0", name="ck_member_read"),
        Index("ix_member_user", "user_id", "conversation_id"),
    )


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    sender_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    client_message_id: Mapped[UUID] = mapped_column()
    sequence: Mapped[int] = mapped_column(BigInteger)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("sender_id", "client_message_id", name="uq_message_client"),
        UniqueConstraint("conversation_id", "sequence", name="uq_message_sequence"),
        ForeignKeyConstraint(
            ["conversation_id", "sender_id"],
            ["conversation_members.conversation_id", "conversation_members.user_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("sequence > 0", name="ck_message_sequence"),
        CheckConstraint("char_length(body) <= 2000", name="ck_message_length"),
        Index(
            "ix_message_unread",
            "conversation_id",
            "sequence",
            "sender_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class MessageReport(Base):
    __tablename__ = "message_reports"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    reporter_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    target_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    message_id: Mapped[UUID | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"))
    conversation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL")
    )
    reason: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(String(1000), default="")
    status: Mapped[str] = mapped_column(String(16), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("reporter_id", "message_id", "reason", name="uq_message_report"),
        CheckConstraint(
            "reason IN ('harassment','spam','impersonation','inappropriate_content',"
            "'suspicious_behavior','other')",
            name="ck_message_report_reason",
        ),
        CheckConstraint(
            "status IN ('open','reviewed','dismissed')", name="ck_message_report_status"
        ),
        Index("ix_message_report_expiry", "expires_at"),
    )
