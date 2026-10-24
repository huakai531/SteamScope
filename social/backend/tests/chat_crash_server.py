"""Disposable loopback test process; intentionally exits only after a committed test send."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
import uvicorn  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from steamscope_social.core.config import Settings  # noqa: E402
from steamscope_social.main import create_app  # noqa: E402

config = Settings()
assert config.environment == "test"
assert make_url(config.database_url.get_secret_value()).database == "steamscope_social_test"
assert config.redis_namespace.startswith("test_")


def no_provider(request):
    raise AssertionError("Provider traffic forbidden")


app = create_app(config, provider_transport=httpx.MockTransport(no_provider))


@app.middleware("http")
async def exit_after_commit(request, call_next):
    response = await call_next(request)
    if (
        request.method == "POST"
        and request.url.path.startswith("/api/v1/conversations/")
        and request.url.path.endswith("/messages")
        and request.headers.get("x-test-crash-after-commit") == "1"
        and response.status_code == 200
    ):
        os._exit(73)
    return response


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(os.environ["SOCIAL_CRASH_TEST_PORT"]),
        access_log=False,
        log_level="critical",
        proxy_headers=False,
    )
