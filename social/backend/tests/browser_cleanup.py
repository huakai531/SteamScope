"""Windows-safe fallback for Playwright process termination; only this fixture run's data."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402

from sqlalchemy import String, cast, delete, or_, select  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from steamscope_social.core.config import Settings  # noqa: E402
from steamscope_social.core.models import SteamAccount, User  # noqa: E402
from steamscope_social.core.resources import Resources  # noqa: E402
from steamscope_social.modules.chat.models import MessageReport
from steamscope_social.modules.social.models import UserReport  # noqa: E402
from steamscope_social.modules.steam.models import RequestBudget  # noqa: E402

DEFAULT_MANIFEST = Path(__file__).resolve().parents[2] / "frontend/test-results/auth-manifest.json"


async def main():
    config = Settings()
    assert config.environment == "test"
    assert make_url(config.database_url.get_secret_value()).database == "steamscope_social_test"
    path = Path(os.environ.get("SOCIAL_BROWSER_MANIFEST", str(DEFAULT_MANIFEST)))
    if not await asyncio.to_thread(path.exists):
        print("No owned browser fixture manifest; nothing to clean")
        return
    values = json.loads(await asyncio.to_thread(path.read_text, encoding="utf-8"))
    assert re.fullmatch(r"browser_[a-f0-9]{32}", values["namespace"])
    assert all(re.fullmatch(r"[0-9]{17}", value) for value in values["identities"])
    config = config.model_copy(update={"redis_namespace": values["namespace"]})
    resources = Resources(config)
    try:
        async with resources.sessions() as db, db.begin():
            ids = select(SteamAccount.user_id).where(
                SteamAccount.steam_id.in_(values["identities"])
            )
            owned_ids = select(cast(SteamAccount.user_id, String)).where(
                SteamAccount.steam_id.in_(values["identities"])
            )
            await db.execute(
                delete(RequestBudget).where(
                    RequestBudget.scope == "user", RequestBudget.owner.in_(owned_ids)
                )
            )
            await db.execute(
                delete(UserReport).where(
                    or_(UserReport.reporter_id.in_(ids), UserReport.target_id.in_(ids))
                )
            )
            await db.execute(
                delete(MessageReport).where(
                    or_(MessageReport.reporter_id.in_(ids), MessageReport.target_id.in_(ids))
                )
            )
            await db.execute(delete(User).where(User.id.in_(ids)))
        keys = [key async for key in resources.redis.scan_iter(match=config.redis_prefix + "*")]
        if keys:
            await resources.redis.delete(*keys)
        print("Only owned browser fixture users and Redis namespace cleaned; no flush")
    finally:
        await resources.close()


if __name__ == "__main__":
    asyncio.run(main())
