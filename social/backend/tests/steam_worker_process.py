"""Disposable test worker process; synthetic HTTP transport, never shipped in images."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from steamscope_social.core.config import Settings  # noqa: E402
from steamscope_social.core.resources import Resources  # noqa: E402
from steamscope_social.modules.steam.client import SteamClient  # noqa: E402
from steamscope_social.modules.steam.jobs import claim_next, process_claim  # noqa: E402
from tests.steam_details_fixtures import transport  # noqa: E402
from tests.steam_fixtures import KEY  # noqa: E402


async def main():
    settings = Settings()
    assert settings.environment == "test"
    assert make_url(settings.database_url.get_secret_value()).database == "steamscope_social_test"
    assert settings.steam_api_key.get_secret_value() == KEY
    settings.steam_requests_per_minute = 100000
    settings.steam_requests_per_day = 100000
    resources = Resources(settings)

    async def external(request):
        if "--pause" in sys.argv:
            print("IN_FLIGHT_AFTER_COMMITTED_CLAIM", flush=True)
            await asyncio.sleep(3600)
        return transport(request)

    try:
        claim = await claim_next(resources, settings)
        assert claim is not None
        await process_claim(
            resources, settings, SteamClient(settings, httpx.MockTransport(external)), claim
        )
        print("PROCESSED_PERSISTED_JOB", flush=True)
    finally:
        await resources.close()


if __name__ == "__main__":
    asyncio.run(main())
