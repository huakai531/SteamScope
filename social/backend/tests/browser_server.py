"""Isolated automated-browser application. Excluded by .dockerignore, not an auth endpoint."""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contextlib import asynccontextmanager  # noqa: E402
from urllib.parse import parse_qs  # noqa: E402

import httpx  # noqa: E402
import uvicorn  # noqa: E402
from pydantic import SecretStr  # noqa: E402
from sqlalchemy import String, cast, delete, or_, select  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from steamscope_social.core.config import Settings  # noqa: E402
from steamscope_social.core.models import SteamAccount, User  # noqa: E402
from steamscope_social.main import create_app  # noqa: E402
from steamscope_social.modules.chat.models import MessageReport
from steamscope_social.modules.social.models import UserReport  # noqa: E402
from steamscope_social.modules.steam.client import SteamClient  # noqa: E402
from steamscope_social.modules.steam.jobs import claim_next, process_claim  # noqa: E402
from steamscope_social.modules.steam.models import RequestBudget  # noqa: E402
from tests.provider_fixtures import SteamTransport  # noqa: E402
from tests.steam_details_fixtures import transport as steam_data_transport
from tests.steam_fixtures import KEY  # noqa: E402

config = Settings()
avatar_directory = tempfile.TemporaryDirectory(prefix="steamscope-browser-avatars-")
config.avatar_storage_dir = Path(avatar_directory.name)
assert config.environment == "test"
assert make_url(config.database_url.get_secret_value()).database == "steamscope_social_test"
assert config.browser_origin == "http://127.0.0.1:3200"
assert config.redis_namespace.startswith("browser_")
if os.environ.get("SOCIAL_BROWSER_STEAM_SYNC") == "1":
    config.steam_api_key = SecretStr(KEY)
    config.steam_requests_per_minute = 100000
    config.steam_requests_per_day = 100000
provider = SteamTransport()
existing: set[str] = set()
owned: set[str] = set()
manifest = Path(
    os.environ.get(
        "SOCIAL_BROWSER_MANIFEST",
        str(Path(__file__).resolve().parents[2] / "frontend/test-results/auth-manifest.json"),
    )
).resolve()


def transport(request):
    if request.method == "POST":
        values = parse_qs(request.content.decode())
        identity = values["openid.claimed_id"][0].rsplit("/", 1)[-1]
        if identity in existing:
            raise RuntimeError("Browser fixture refuses a pre-existing test identity")
        owned.add(identity)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        temporary = manifest.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"identities": sorted(owned), "namespace": config.redis_namespace}),
            encoding="utf-8",
        )
        temporary.replace(manifest)
    return provider(request)


app = create_app(config, provider_transport=httpx.MockTransport(transport))
original_lifespan = app.router.lifespan_context


@asynccontextmanager
async def lifespan(application):
    async with original_lifespan(application):
        resources = application.state.resources
        async with resources.sessions() as db:
            existing.update((await db.scalars(select(SteamAccount.steam_id))).all())

        async def fixture_worker():
            while True:
                claim = await claim_next(resources, config)
                if claim:
                    await process_claim(
                        resources,
                        config,
                        SteamClient(config, httpx.MockTransport(steam_data_transport)),
                        claim,
                    )
                await asyncio.sleep(0.1)

        worker = asyncio.create_task(fixture_worker())
        try:
            yield
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
            async with resources.sessions() as db, db.begin():
                ids = select(SteamAccount.user_id).where(
                    SteamAccount.steam_id.in_(owned - existing)
                )
                owned_ids = select(cast(SteamAccount.user_id, String)).where(
                    SteamAccount.steam_id.in_(owned - existing)
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
            avatar_directory.cleanup()


app.router.lifespan_context = lifespan

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8200, access_log=False, proxy_headers=False)
