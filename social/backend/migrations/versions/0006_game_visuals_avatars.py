"""Independent platform avatars, with durable storage deletion outbox."""

import sqlalchemy as sa
from alembic import op

revision = "0006_game_visuals_avatars"
down_revision = "0005_phase6_chat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_key", sa.String(37), nullable=True))
    op.add_column(
        "users", sa.Column("avatar_updated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        "ck_users_avatar_key", "users", "avatar_key IS NULL OR avatar_key ~ '^[a-f0-9]{32}\\.webp$'"
    )
    op.create_table(
        "avatar_deletions",
        sa.Column("key", sa.String(37), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("key ~ '^[a-f0-9]{32}\\.webp$'", name="ck_avatar_deletion_key"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM users WHERE avatar_key IS NOT NULL) "
            "OR EXISTS (SELECT 1 FROM avatar_deletions)"
        )
    ):
        raise RuntimeError("Refusing downgrade with existing avatar data")
    op.drop_table("avatar_deletions")
    op.drop_constraint("ck_users_avatar_key", "users", type_="check")
    op.drop_column("users", "avatar_updated_at")
    op.drop_column("users", "avatar_key")
