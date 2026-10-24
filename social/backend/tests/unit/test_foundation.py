import asyncio
import logging
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from steamscope_social.core.config import Settings
from steamscope_social.core.resources import Resources
from steamscope_social.main import create_app
from steamscope_social.worker.__main__ import run


def test_liveness_never_calls_dependencies(settings, monkeypatch):
    monkeypatch.setattr(Resources, "readiness", AsyncMock(side_effect=AssertionError("no calls")))
    with TestClient(create_app(settings)) as client:
        assert client.get("/health/live").json() == {"status": "alive"}
        assert client.get("/api/v1/system").json()["subphase"] == "6"


@pytest.mark.parametrize(
    "pg_ok,redis_ok,code",
    [(True, True, 200), (False, True, 503), (True, False, 503), (False, False, 503)],
)
def test_readiness_actual_probe_paths(settings, monkeypatch, pg_ok, redis_ok, code):
    secret = "password=DO_NOT_EXPOSE_INTERNALS"
    pg = AsyncMock(side_effect=None if pg_ok else RuntimeError(secret))
    redis = AsyncMock(side_effect=None if redis_ok else RuntimeError(secret))
    monkeypatch.setattr(Resources, "postgres_ping", pg)
    monkeypatch.setattr(Resources, "redis_ping", redis)
    with TestClient(create_app(settings)) as client:
        response = client.get("/health/ready")
    assert response.status_code == code
    assert response.json()["dependencies"] == {
        "postgres": "up" if pg_ok else "down",
        "redis": "up" if redis_ok else "down",
    }
    assert secret not in response.text
    assert response.headers["cache-control"] == "no-store"
    pg.assert_awaited_once()
    redis.assert_awaited_once()


async def test_probe_is_bounded(settings):
    resources = Resources(settings)
    try:

        async def stalled():
            await asyncio.sleep(30)

        assert await asyncio.wait_for(resources.probe("postgres", stalled), 0.5) is False
    finally:
        await resources.close()


@pytest.mark.parametrize(
    "database", ["steamscope", "steamscope_test", "steamscope_social_dev", "postgres"]
)
def test_test_settings_refuse_wrong_database(database):
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="test",
            database_url=f"postgresql+asyncpg://u:p@localhost/{database}",
        )


def test_settings_hide_secret_on_failure():
    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None, database_url="postgresql+asyncpg://u:SENTINEL_SECRET@localhost/legacy"
        )
    assert "SENTINEL_SECRET" not in str(error.value)


def test_environment_config(monkeypatch):
    monkeypatch.setenv("SOCIAL_ENVIRONMENT", "test")
    monkeypatch.setenv(
        "SOCIAL_DATABASE_URL", "postgresql+asyncpg://u:p@localhost/steamscope_social_test"
    )
    config = Settings(_env_file=None)
    assert config.environment == "test"
    assert "u:p" not in repr(config)


def test_cors_and_safe_errors(settings):
    app = create_app(settings)

    @app.get("/test-error", include_in_schema=False)
    async def failure():
        raise RuntimeError("SECRET_SQL_CONNECTION")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/test-error")
        assert response.status_code == 500
        assert "SECRET_SQL_CONNECTION" not in response.text
        assert response.headers["x-request-id"]
        allowed = client.get("/health/live", headers={"Origin": "http://127.0.0.1:3100"})
        denied = client.get("/health/live", headers={"Origin": "https://attacker.invalid"})
        assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:3100"
        assert "access-control-allow-origin" not in denied.headers


async def test_worker_shutdown_and_failure(settings, monkeypatch, caplog):
    monkeypatch.setattr(
        "steamscope_social.worker.__main__.claim_next", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(Resources, "postgres_ping", AsyncMock())
    monkeypatch.setattr(Resources, "redis_ping", AsyncMock())
    closed = AsyncMock()
    monkeypatch.setattr(Resources, "close", closed)
    stop = asyncio.Event()
    with caplog.at_level(logging.INFO, logger="steamscope_social.worker"):
        task = asyncio.create_task(run(settings, stop))
        await asyncio.sleep(0.01)
        stop.set()
        assert await asyncio.wait_for(task, 1) == 0
    assert "worker_started:steam_sync" in caplog.text
    closed.assert_awaited_once()
    monkeypatch.setattr(Resources, "postgres_ping", AsyncMock(side_effect=OSError("secret")))
    assert await run(settings, asyncio.Event(), check=True) == 1
