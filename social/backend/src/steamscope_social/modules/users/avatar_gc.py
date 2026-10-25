"""Explicit local-store crash recovery: only unreferenced opaque files older than 24h."""

import asyncio
import logging
import time

from sqlalchemy import select

from steamscope_social.core.config import Settings
from steamscope_social.core.resources import Resources
from steamscope_social.modules.users.avatars import KEY, drain_avatar_deletions, retire_avatar
from steamscope_social.modules.users.models import User


async def reconcile(resources: Resources, config: Settings) -> int:
    root = config.avatar_storage_path.resolve()
    if not root.is_dir():
        return 0
    count = 0
    # Scan names only in the managed directory, never follow links or recurse.
    for path in root.iterdir():
        if count == 100:
            break
        if not KEY.fullmatch(path.name) or path.is_symlink() or not path.is_file():
            continue
        if path.stat().st_mtime > time.time() - 86400:
            continue
        async with resources.sessions() as db, db.begin():
            if await db.scalar(select(User.id).where(User.avatar_key == path.name)):
                continue
            await retire_avatar(db, path.name)
            count += 1
    await drain_avatar_deletions(resources, config)
    return count


async def main() -> None:
    config = Settings()
    resources = Resources(config)
    try:
        count = await reconcile(resources, config)
        print(f"Unreferenced old avatars queued: {count}")
    finally:
        await resources.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
