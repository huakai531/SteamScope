import os

import pytest

from steamscope_social.core.config import Settings


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://fixture:fixture@127.0.0.1:55433/steamscope_social_test",
        redis_url="redis://127.0.0.1:56379/1",
        dependency_timeout_seconds=0.1,
    )


def pytest_collection_modifyitems(items):
    if os.environ.get("SOCIAL_INTEGRATION") != "1":
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(
                    pytest.mark.skip(reason="Real services require SOCIAL_INTEGRATION=1")
                )
