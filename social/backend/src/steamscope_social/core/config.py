from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

SOCIAL_ROOT = Path(__file__).resolve().parents[4]
DATABASES = {
    "development": {"steamscope_social_dev"},
    "test": {"steamscope_social_test", "steamscope_social_migration_test"},
    "production": {"steamscope_social_prod"},
}


def verify_database(url: str, environment: str) -> None:
    """Fail closed before a connection or mutation, including Alembic."""
    try:
        parsed = make_url(url)
        valid = (
            parsed.drivername == "postgresql+asyncpg"
            and parsed.database in DATABASES.get(environment, set())
            and bool(parsed.host)
            and not parsed.query
        )
    except Exception:
        valid = False
    if not valid:
        raise ValueError("Use the isolated SteamScope social database for this environment")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SOCIAL_",
        env_file=SOCIAL_ROOT / ".env",
        extra="ignore",
        hide_input_in_errors=True,
    )
    environment: Literal["development", "test", "production"] = "development"
    avatar_storage_dir: Path | None = None

    @property
    def avatar_storage_path(self) -> Path:
        return self.avatar_storage_dir or SOCIAL_ROOT / "storage" / self.environment / "avatars"

    database_url: SecretStr = SecretStr(
        "postgresql+asyncpg://steamscope_social:local_only_change_me@127.0.0.1:55433/"
        "steamscope_social_dev"
    )
    redis_url: SecretStr = SecretStr("redis://127.0.0.1:56379/0")
    dependency_timeout_seconds: float = Field(default=2, ge=0.05, le=10)
    cors_origins: list[str] = ["http://localhost:3100", "http://127.0.0.1:3100"]
    worker_check_interval_seconds: float = Field(default=10, ge=0.1, le=60)
    browser_origin: str = "http://127.0.0.1:3100"
    cookie_secure: bool = False
    session_absolute_seconds: int = Field(default=604800, ge=300, le=2592000)
    session_idle_seconds: int = Field(default=86400, ge=60, le=604800)
    recent_auth_seconds: int = Field(default=600, ge=60, le=1800)
    login_attempt_seconds: int = Field(default=300, ge=60, le=600)
    provider_timeout_seconds: float = Field(default=5, ge=0.1, le=10)
    auth_rate_limit: int = Field(default=10, ge=1, le=1000)
    sensitive_rate_limit: int = Field(default=30, ge=1, le=1000)
    redis_namespace: str = Field(default="phase2", pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    steam_api_key: SecretStr = SecretStr("")
    steam_sync_lease_seconds: int = Field(default=90, ge=45, le=300)
    steam_sync_max_attempts: int = Field(default=3, ge=1, le=5)
    steam_sync_cooldown_seconds: int = Field(default=300, ge=60, le=86400)
    steam_sync_poll_seconds: float = Field(default=2, ge=0.1, le=30)
    steam_schema_ttl_seconds: int = Field(default=86400, ge=60, le=604800)
    steam_requests_per_minute: int = Field(default=30, ge=3, le=60)
    steam_requests_per_day: int = Field(default=1000, ge=3, le=10000)
    steam_user_requests_per_hour: int = Field(default=12, ge=3, le=60)

    @property
    def callback_url(self) -> str:
        return self.browser_origin + "/api/v1/auth/steam/callback"

    @property
    def redis_prefix(self) -> str:
        return f"steamscope:social:{self.environment}:{self.redis_namespace}:"

    @field_validator("redis_url")
    @classmethod
    def redis_origin(cls, value: SecretStr) -> SecretStr:
        try:
            parsed = urlsplit(value.get_secret_value())
            valid = (
                parsed.scheme in {"redis", "rediss"}
                and bool(parsed.hostname)
                and parsed.path in {"/0", "/1"}
                and not parsed.query
                and not parsed.fragment
            )
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("Use an explicit Redis URL with database 0 or 1")
        return value

    @field_validator("cors_origins")
    @classmethod
    def explicit_origins(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username
            ):
                raise ValueError("CORS origins must be explicit HTTP origins")
        return origins

    @model_validator(mode="after")
    def isolated_database(self) -> "Settings":
        verify_database(self.database_url.get_secret_value(), self.environment)
        origin = urlsplit(self.browser_origin)
        if (
            origin.scheme not in {"http", "https"}
            or not origin.hostname
            or origin.username
            or origin.password
            or origin.path
            or origin.query
            or origin.fragment
        ):
            raise ValueError("Use one explicit browser origin without a path")
        if not self.cookie_secure and (
            self.environment == "production"
            or origin.scheme != "http"
            or origin.hostname != "127.0.0.1"
        ):
            raise ValueError("Non-Secure cookies are limited to loopback HTTP development/test")
        if self.cookie_secure and origin.scheme != "https":
            raise ValueError("Secure cookies require an HTTPS browser origin")
        if self.session_idle_seconds > self.session_absolute_seconds:
            raise ValueError("Idle timeout must not exceed absolute timeout")
        return self
