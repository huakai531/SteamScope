import asyncio
import subprocess
import sys

import pytest
from sqlalchemy import text

from steamscope_social.core.config import Settings
from steamscope_social.core.resources import Resources
from steamscope_social.worker.__main__ import run

pytestmark = pytest.mark.integration


async def test_real_postgres_redis_and_phase2_tables():
    settings = Settings()
    assert settings.environment == "test", "Integration must use isolated test configuration"
    resources = Resources(settings)
    try:
        assert (await resources.readiness()).status == "ready"
        async with resources.engine.connect() as connection:
            name = await connection.scalar(text("SELECT current_database()"))
            assert name == "steamscope_social_test"
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


def test_real_alembic_and_worker_process():
    settings = Settings()
    assert settings.environment == "test"
    for command in (
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        [sys.executable, "-m", "steamscope_social.worker", "--check"],
    ):
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, "Isolated migration/worker check failed; inspect safe logs"


async def test_real_worker_clean_stop():
    settings = Settings()
    assert settings.environment == "test"
    stop = asyncio.Event()
    stop.set()
    assert await run(settings, stop) == 0
