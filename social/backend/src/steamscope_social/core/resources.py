import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Literal

from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from steamscope_social.core.config import Settings

logger = logging.getLogger("steamscope_social.dependencies")


class Dependencies(BaseModel):
    postgres: Literal["up", "down"]
    redis: Literal["up", "down"]


class Readiness(BaseModel):
    status: Literal["ready", "unavailable"]
    scope: Literal["foundation"] = "foundation"
    dependencies: Dependencies


class Resources:
    def __init__(self, settings: Settings) -> None:
        self.timeout = settings.dependency_timeout_seconds
        self.engine = create_async_engine(
            settings.database_url.get_secret_value(),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            pool_timeout=self.timeout,
            hide_parameters=True,
            connect_args={"timeout": self.timeout, "command_timeout": self.timeout},
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.redis: Redis = Redis.from_url(
            settings.redis_url.get_secret_value(),
            socket_connect_timeout=self.timeout,
            socket_timeout=self.timeout,
            decode_responses=True,
        )

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessions() as session:
            yield session

    async def postgres_ping(self) -> None:
        async with self.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def redis_ping(self) -> None:
        await self.redis.ping()

    async def probe(self, name: str, operation: Callable[[], Awaitable[None]]) -> bool:
        try:
            async with asyncio.timeout(self.timeout):
                await operation()
            return True
        except Exception:
            logger.warning("dependency_unavailable:%s", name)
            return False

    async def readiness(self) -> Readiness:
        pg, redis = await asyncio.gather(
            self.probe("postgres", self.postgres_ping), self.probe("redis", self.redis_ping)
        )
        return Readiness(
            status="ready" if pg and redis else "unavailable",
            dependencies=Dependencies(
                postgres="up" if pg else "down", redis="up" if redis else "down"
            ),
        )

    async def close(self) -> None:
        try:
            await self.redis.aclose()
        finally:
            await self.engine.dispose()
