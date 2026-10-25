import asyncio
import subprocess
import sys

import pytest
from sqlalchemy import text

from steamscope_social.core.config import Settings
from steamscope_social.core.resources import Resources

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


async def test_isolated_postgres_and_current_migration():
    settings = Settings()
    assert settings.environment == "test"
    migration = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert migration.returncode == 0, "Migration failed; inspect local safe diagnostics"
    resources = Resources(settings)
    try:
        await resources.postgres_ping()
        async with resources.engine.connect() as connection:
            assert (
                await connection.scalar(text("SELECT current_database()"))
                == "steamscope_social_test"
            )
            tables = (
                (
                    await connection.execute(
                        text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                    )
                )
                .scalars()
                .all()
            )
            assert set(tables) == {
                "avatar_deletions",
                "conversations",
                "conversation_members",
                "messages",
                "message_reports",
                "connection_requests",
                "connections",
                "user_blocks",
                "user_reports",
                "social_notifications",
                "alembic_version",
                "steam_achievement_schemas",
                "steam_achievement_states",
                "steam_achievement_definitions",
                "steam_user_achievements",
                "steam_friends",
                "users",
                "steam_accounts",
                "user_sessions",
                "privacy_settings",
                "audit_logs",
                "login_attempts",
                "games",
                "user_games",
                "steam_recent_games",
                "steam_resource_states",
                "steam_sync_jobs",
                "steam_sync_runs",
                "steam_request_budgets",
            }
    finally:
        await resources.close()
