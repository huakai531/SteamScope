"""Phase 2 identities, sessions, privacy, audit and one-time login transactions."""

import sqlalchemy as sa
from alembic import op

revision = "0001_phase2_accounts"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("handle", sa.String(24), nullable=False),
        sa.Column("display_name", sa.String(60), nullable=False),
        sa.Column("biography", sa.String(500), nullable=False),
        sa.Column("locale", sa.String(16), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("handle ~ '^[A-Za-z][A-Za-z0-9_]{2,23}$'", name="ck_users_handle"),
        sa.CheckConstraint("status IN ('active','disabled','deleting')", name="ck_users_status"),
    )
    op.create_index("uq_users_handle_ci", "users", [sa.text("lower(handle)")], unique=True)
    op.create_table(
        "steam_accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("steam_id", sa.String(20), nullable=False, unique=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("steam_id ~ '^[0-9]{17}$'", name="ck_steam_accounts_id"),
    )
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("token_digest", sa.String(64), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("authenticated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("expires_at > created_at", name="ck_sessions_expiry"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])
    columns = [
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        )
    ]
    for field in ("profile", "library", "playtime", "achievements", "presence"):
        columns.extend(
            [
                sa.Column(field, sa.String(16), nullable=False),
                sa.CheckConstraint(
                    f"{field} IN ('private','connections','public')", name=f"ck_privacy_{field}"
                ),
            ]
        )
    op.create_table(
        "privacy_settings",
        *columns,
        sa.Column("discovery", sa.Boolean(), nullable=False),
        sa.Column("connection_requests", sa.String(16), nullable=False),
        sa.Column("messaging", sa.String(16), nullable=False),
        sa.CheckConstraint(
            "connection_requests IN ('nobody','discoverable')", name="ck_privacy_requests"
        ),
        sa.CheckConstraint("messaging IN ('nobody','connections')", name="ck_privacy_messaging"),
    )
    op.create_table(
        "login_attempts",
        sa.Column("state_digest", sa.String(64), primary_key=True),
        sa.Column("browser_digest", sa.String(64), nullable=False),
        sa.Column("purpose", sa.String(12), nullable=False),
        sa.Column("destination", sa.String(64), nullable=False),
        sa.Column("bound_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column(
            "bound_session_id", sa.Uuid(), sa.ForeignKey("user_sessions.id", ondelete="CASCADE")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("purpose IN ('login','reauth')", name="ck_login_attempt_purpose"),
        sa.CheckConstraint("expires_at > created_at", name="ck_login_attempt_expiry"),
        sa.CheckConstraint(
            "purpose != 'reauth' OR (bound_user_id IS NOT NULL AND bound_session_id IS NOT NULL)",
            name="ck_login_attempt_binding",
        ),
    )
    op.create_index("ix_login_attempts_expires_at", "login_attempts", ["expires_at"])
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("event", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade():
    for table in (
        "audit_logs",
        "login_attempts",
        "privacy_settings",
        "user_sessions",
        "steam_accounts",
        "users",
    ):
        op.drop_table(table)
