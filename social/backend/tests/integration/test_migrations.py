import asyncio
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import delete, insert, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from steamscope_social.core.config import Settings
from steamscope_social.core.database import utcnow
from steamscope_social.modules.auth.models import UserSession
from steamscope_social.modules.chat.models import Conversation
from steamscope_social.modules.privacy.models import PrivacySettings
from steamscope_social.modules.steam.models import (
    AchievementDefinition,
    AchievementSchema,
    AchievementState,
    SteamFriend,
    UserAchievement,
)
from steamscope_social.modules.users.models import User

pytestmark = pytest.mark.integration
DATABASE = "steamscope_social_migration_test"
BACKEND = Path(__file__).resolve().parents[2]
TABLES = {
    "conversations",
    "conversation_members",
    "messages",
    "message_reports",
    "connection_requests",
    "connections",
    "user_blocks",
    "user_reports",
    "social_notifications",
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


async def test_fresh_migration_constraints_and_disposable_rollback_reupgrade():
    current = Settings()
    url = make_url(current.database_url.get_secret_value())
    assert current.environment == "test" and url.database == "steamscope_social_test"
    admin = create_async_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
        hide_parameters=True,
    )
    try:
        async with admin.connect() as connection:
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": DATABASE}
            )
            if not exists:
                await connection.execute(text("CREATE DATABASE steamscope_social_migration_test"))
    finally:
        await admin.dispose()
    disposable = url.set(database=DATABASE)
    assert disposable.database != url.database and disposable.database == DATABASE
    env = dict(
        os.environ,
        SOCIAL_ENVIRONMENT="test",
        SOCIAL_DATABASE_URL=disposable.render_as_string(hide_password=False),
    )
    engine = create_async_engine(disposable, poolclass=NullPool, hide_parameters=True)

    async def command(
        *args, expected=0, failure_message="Refuse Phase 3B downgrade with imported data"
    ):
        result = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "alembic", *args],
            cwd=BACKEND,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == expected, f"Disposable migration {args} unexpected exit"
        if expected:
            assert failure_message in result.stderr

    async def tables():
        async with engine.connect() as connection:
            return set(
                (
                    await connection.scalars(
                        text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                    )
                ).all()
            )

    try:
        existing = await tables()
        assert existing <= TABLES | {"alembic_version"}, (
            "Refuse unrelated disposable database tables"
        )
        async with engine.connect() as connection:
            for name in sorted(existing & TABLES):
                assert await connection.scalar(text('SELECT count(*) FROM "' + name + '"')) == 0, (
                    "Refuse rollback of nonempty database"
                )
        # Reset only this explicitly named, empty disposable migration database.
        if existing & TABLES:
            await command("downgrade", "base")
        assert await tables() <= {"alembic_version"}
        await command("upgrade", "0001_phase2_accounts")
        owner, link, session = uuid4(), uuid4(), uuid4()
        async with engine.begin() as connection:
            await connection.execute(
                insert(User).values(
                    id=owner, handle="migration_fixture", display_name="Keep platform name"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO steam_accounts(id,user_id,steam_id,verified_at,linked_at) "
                    "VALUES(:id,:owner,'76561198000000011',now(),now())"
                ),
                {"id": link, "owner": owner},
            )
            await connection.execute(
                insert(UserSession).values(
                    id=session,
                    user_id=owner,
                    token_digest="0" * 64,
                    expires_at=utcnow() + timedelta(days=1),
                )
            )
            await connection.execute(insert(PrivacySettings).values(user_id=owner))
        await command("upgrade", "0002_phase3a_steam_sync")
        async with engine.begin() as connection:
            await connection.execute(
                text("INSERT INTO games(app_id,name) VALUES(77830001,'Migration synthetic game')")
            )
            await connection.execute(
                text(
                    "INSERT INTO user_games(user_id,app_id,"
                    "total_minutes,recent_minutes,observed_at) "
                    "VALUES(:owner,77830001,187,17,now())"
                ),
                {"owner": owner},
            )
            await connection.execute(
                text(
                    "INSERT INTO steam_recent_games(user_id,app_id,"
                    "total_minutes,recent_minutes,observed_at) "
                    "VALUES(:owner,77830001,187,17,now())"
                ),
                {"owner": owner},
            )
            await connection.execute(
                text(
                    "INSERT INTO steam_resource_states(user_id,resource,status,code,"
                    "last_success_at,snapshot_id,exposed) "
                    "VALUES(:owner,'library','populated','OK',now(),:snapshot,true)"
                ),
                {"owner": owner, "snapshot": uuid4()},
            )
            await connection.execute(
                text(
                    "INSERT INTO steam_sync_jobs(id,user_id,link_id,generation,status,attempts,"
                    "created_at,available_at,outcomes) "
                    "VALUES(:id,:owner,:link,0,'succeeded',1,now(),now(),'{}')"
                ),
                {"id": uuid4(), "owner": owner, "link": link},
            )
        await command("upgrade", "0003_phase3b_steam_details")
        await command("upgrade", "head")
        assert await tables() == TABLES | {"alembic_version"}
        await command("check")
        async with engine.connect() as connection:
            constraints = (
                await connection.execute(
                    text(
                        "SELECT conname, contype::text AS contype, "
                        "confdeltype::text AS confdeltype FROM pg_constraint "
                        "WHERE connamespace='public'::regnamespace"
                    )
                )
            ).all()
            assert sum(row.contype == "f" for row in constraints) == 43
            assert any(row.contype == "f" and row.confdeltype == "n" for row in constraints)
            indexes = dict(
                (
                    await connection.execute(
                        text("SELECT indexname,indexdef FROM pg_indexes WHERE schemaname='public'")
                    )
                ).all()
            )
            assert "UNIQUE" in indexes["uq_sync_active_scope"]
            assert "WHERE" in indexes["uq_sync_active_scope"]
            assert "ix_sync_claim" in indexes
            assert "steam_user_achievements_pkey" in indexes
            assert "steam_friends_pkey" in indexes
            assert "UNIQUE" in indexes["uq_request_pending_pair"]
            assert "WHERE" in indexes["uq_request_pending_pair"]
            assert "UNIQUE" in indexes["uq_notification_event"]
        partner = uuid4()
        async with engine.begin() as connection:
            await connection.execute(
                insert(User).values(
                    id=partner, handle="migration_partner", display_name="Synthetic partner"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO user_blocks(blocker_id,blocked_id,created_at) VALUES(:a,:b,now())"
                ),
                dict(a=owner, b=partner),
            )
        conversation_id = uuid4()
        async with engine.begin() as connection:
            await connection.execute(
                insert(Conversation).values(
                    id=conversation_id,
                    user_id_low=min(owner, partner),
                    user_id_high=max(owner, partner),
                )
            )
        await command(
            "downgrade",
            "0004_phase5_social",
            expected=1,
            failure_message="Refusing downgrade with existing Phase 6 data",
        )
        async with engine.begin() as connection:
            assert (
                await connection.scalar(
                    text("SELECT count(*) FROM conversations WHERE id=:id"),
                    dict(id=conversation_id),
                )
                == 1
            )
            assert (
                await connection.scalar(text("SELECT version_num FROM alembic_version"))
                == "0005_phase6_chat"
            )
            await connection.execute(delete(Conversation).where(Conversation.id == conversation_id))
        await command(
            "downgrade",
            "0003_phase3b_steam_details",
            expected=1,
            failure_message="Refusing downgrade with existing Phase 5 data",
        )
        async with engine.begin() as connection:
            assert (
                await connection.scalar(
                    text("SELECT count(*) FROM user_blocks WHERE blocker_id=:id"), dict(id=owner)
                )
                == 1
            )
            assert (
                await connection.scalar(text("SELECT version_num FROM alembic_version"))
                == "0005_phase6_chat"
            )
            await connection.execute(delete(User).where(User.id == partner))
        for revision in ("0002_phase3a_steam_sync", "head"):
            await command("downgrade" if revision.startswith("0002") else "upgrade", revision)
            async with engine.connect() as connection:
                assert (
                    await connection.scalar(
                        text("SELECT total_minutes FROM user_games WHERE user_id=:id"),
                        {"id": owner},
                    )
                    == 187
                )
                assert (
                    await connection.scalar(
                        text("SELECT recent_minutes FROM steam_recent_games WHERE user_id=:id"),
                        {"id": owner},
                    )
                    == 17
                )
                assert (
                    await connection.scalar(
                        text(
                            "SELECT count(*) FROM steam_resource_states "
                            "WHERE user_id=:id AND exposed"
                        ),
                        {"id": owner},
                    )
                    == 1
                )
                assert (
                    await connection.scalar(
                        text("SELECT count(*) FROM steam_sync_jobs WHERE user_id=:id"),
                        {"id": owner},
                    )
                    == 1
                )
                assert (
                    await connection.scalar(
                        text("SELECT display_name FROM users WHERE id=:id"), {"id": owner}
                    )
                    == "Keep platform name"
                )
                assert (
                    await connection.scalar(
                        text("SELECT count(*) FROM user_sessions WHERE id=:id"), {"id": session}
                    )
                    == 1
                )
                assert (
                    await connection.scalar(
                        text("SELECT count(*) FROM privacy_settings WHERE user_id=:id"),
                        {"id": owner},
                    )
                    == 1
                )
                assert (
                    await connection.scalar(
                        text("SELECT steam_id FROM steam_accounts WHERE id=:id"), {"id": link}
                    )
                    == "76561198000000011"
                )
        # Existing 3B imports survive a no-op head upgrade; destructive downgrade
        # must refuse them atomically. Only this disposable fixture is erased below.
        observed = utcnow()
        async with engine.begin() as connection:
            await connection.execute(
                insert(AchievementSchema).values(
                    app_id=77830001,
                    language="english",
                    revision="a" * 64,
                    status="populated",
                    last_success_at=observed,
                )
            )
            await connection.execute(
                insert(AchievementDefinition).values(
                    app_id=77830001,
                    language="english",
                    api_name="FIXTURE",
                    hidden=False,
                )
            )
            await connection.execute(
                insert(AchievementState).values(
                    user_id=owner,
                    app_id=77830001,
                    status="populated",
                    exposed=True,
                    schema_revision="a" * 64,
                    snapshot_id=uuid4(),
                    last_success_at=observed,
                )
            )
            await connection.execute(
                insert(UserAchievement).values(
                    user_id=owner,
                    app_id=77830001,
                    api_name="FIXTURE",
                    unlocked=True,
                    unlocked_at=observed,
                    observed_at=observed,
                )
            )
            await connection.execute(
                insert(SteamFriend).values(
                    user_id=owner,
                    friend_steam_id64="76561198000000012",
                    observed_at=observed,
                )
            )

        async def contents():
            async with engine.connect() as connection:
                return {
                    name: await connection.scalar(
                        text(
                            "SELECT md5(coalesce(string_agg(row_to_json(t)::text, '' "
                            "ORDER BY row_to_json(t)::text), '')) FROM " + name + " t"
                        )
                    )
                    for name in TABLES | {"alembic_version"}
                }

        before = await contents()
        await command("upgrade", "head")
        assert await contents() == before
        await command("downgrade", "0002_phase3a_steam_sync", expected=1)
        assert await contents() == before
        async with engine.begin() as connection:
            assert (
                await connection.scalar(
                    text("SELECT import_generation FROM steam_accounts WHERE id=:id"), {"id": link}
                )
                == 0
            )
            await connection.execute(delete(User).where(User.id == owner))
            await connection.execute(
                delete(AchievementSchema).where(AchievementSchema.app_id == 77830001)
            )
            await connection.execute(text("DELETE FROM games WHERE app_id=77830001"))
        await command("downgrade", "base")
        await command("upgrade", "head")
        assert await tables() == TABLES | {"alembic_version"}
        await command("downgrade", "base")
        assert await tables() == {"alembic_version"}
        await command("upgrade", "head")
        await command("current")
        assert await tables() == TABLES | {"alembic_version"}
    finally:
        await engine.dispose()
