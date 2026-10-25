import secrets
from contextlib import AsyncExitStack
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import String, cast, delete, select
from sqlalchemy.engine import make_url

from steamscope_social.core.config import Settings
from steamscope_social.core.models import LoginAttempt, SteamAccount, User
from steamscope_social.main import create_app
from steamscope_social.modules.auth.security import digest
from steamscope_social.modules.steam.models import RequestBudget
from tests.provider_fixtures import SteamTransport, assertion


class AuthHarness:
    def __init__(self, app, stack, provider):
        self.app, self.stack, self.provider = app, stack, provider
        self.config = app.state.config
        self.resources = app.state.resources
        self.identities = []
        self.attempts = []

    def identity(self):
        value = str(76561197960265728 + secrets.randbelow(2147483647))
        self.identities.append(value)
        return value

    async def client(self):
        return await self.stack.enter_async_context(
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self.app),
                base_url=self.config.browser_origin,
                follow_redirects=False,
            )
        )

    async def start(self, client, reauth=False):
        if reauth:
            response = await client.post(
                "/api/v1/auth/steam/reauth", headers=await self.headers(client)
            )
            assert response.status_code == 200, response.text
            url = response.json()["url"]
        else:
            response = await client.get("/api/v1/auth/steam/login")
            assert response.status_code == 303, response.text
            url = response.headers["location"]
        state = parse_qs(urlsplit(parse_qs(urlsplit(url).query)["openid.return_to"][0]).query)[
            "state"
        ][0]
        self.attempts.append(digest(state))
        return url

    async def login(self, client, identity=None):
        params = assertion(await self.start(client), identity or self.identity())
        response = await client.get("/api/v1/auth/steam/callback", params=params)
        assert response.status_code == 303 and response.headers["location"].endswith("/account")
        return (await client.get("/api/v1/me")).json()

    async def headers(self, client):
        response = await client.get("/api/v1/auth/csrf")
        assert response.status_code == 200
        return {"Origin": self.config.browser_origin, "X-CSRF-Token": response.json()["csrf_token"]}


@pytest.fixture
async def auth(tmp_path):
    config = Settings()
    assert config.environment == "test"
    assert make_url(config.database_url.get_secret_value()).database == "steamscope_social_test"
    config = config.model_copy(
        update={
            "avatar_storage_dir": tmp_path / "avatars",
            "redis_namespace": "test_" + uuid4().hex,
            "auth_rate_limit": 1000,
            "sensitive_rate_limit": 1000,
        }
    )
    provider = SteamTransport()
    app = create_app(config, provider_transport=httpx.MockTransport(provider))
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(app.router.lifespan_context(app))
        harness = AuthHarness(app, stack, provider)
        try:
            yield harness
        finally:
            async with harness.resources.sessions() as db, db.begin():
                await db.execute(
                    delete(LoginAttempt).where(LoginAttempt.state_digest.in_(harness.attempts))
                )
                ids = select(SteamAccount.user_id).where(
                    SteamAccount.steam_id.in_(harness.identities)
                )
                owned_ids = select(cast(SteamAccount.user_id, String)).where(
                    SteamAccount.steam_id.in_(harness.identities)
                )
                await db.execute(
                    delete(RequestBudget).where(
                        RequestBudget.scope == "user", RequestBudget.owner.in_(owned_ids)
                    )
                )
                await db.execute(delete(User).where(User.id.in_(ids)))
            keys = [
                key
                async for key in harness.resources.redis.scan_iter(match=config.redis_prefix + "*")
            ]
            if keys:
                await harness.resources.redis.delete(*keys)
