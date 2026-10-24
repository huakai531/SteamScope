import asyncio
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from steamscope_social.modules.auth.security import session_cookie
from tests.integration.test_chat import chat  # noqa: F401
from tests.integration.test_players import players  # noqa: F401
from tests.integration.test_social import social  # noqa: F401

pytestmark = pytest.mark.integration
BACKEND = Path(__file__).resolve().parents[2]


async def test_api_process_dies_after_commit_before_acknowledgement(chat, unused_tcp_port):  # noqa: F811
    auth, clients, _, _, _, _, cid, send = chat
    env = dict(
        os.environ,
        SOCIAL_ENVIRONMENT="test",
        SOCIAL_DATABASE_URL=auth.config.database_url.get_secret_value(),
        SOCIAL_REDIS_URL=auth.config.redis_url.get_secret_value(),
        SOCIAL_REDIS_NAMESPACE=auth.config.redis_namespace,
        SOCIAL_STEAM_API_KEY="",
        SOCIAL_BROWSER_ORIGIN=auth.config.browser_origin,
        SOCIAL_CRASH_TEST_PORT=str(unused_tcp_port),
    )
    process = await asyncio.to_thread(
        subprocess.Popen,
        [sys.executable, "tests/chat_crash_server.py"],
        cwd=BACKEND,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    key = uuid4()
    try:
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{unused_tcp_port}", trust_env=False, timeout=3
        ) as client:
            async with asyncio.timeout(10):
                while True:
                    assert process.poll() is None, "Disposable test server exited before readiness"
                    try:
                        if (await client.get("/health/live")).status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    await asyncio.sleep(0.05)
            headers = await auth.headers(clients["A"])
            headers.update(
                {
                    "Cookie": session_cookie(auth.config)
                    + "="
                    + clients["A"].cookies[session_cookie(auth.config)],
                    "x-test-crash-after-commit": "1",
                }
            )
            with pytest.raises(httpx.TransportError):
                await client.post(
                    f"/api/v1/conversations/{cid}/messages",
                    headers=headers,
                    json={
                        "client_message_id": str(key),
                        "body": "Synthetic committed before process exit",
                    },
                )
        assert await asyncio.to_thread(process.wait, 5) == 73
        history = (await clients["B"].get(f"/api/v1/conversations/{cid}/messages")).json()["items"]
        assert len(history) == 1
        retry = await send(body="Synthetic committed before process exit", mid=key)
        assert retry.status_code == 200 and retry.json()["id"] == history[0]["id"]
        assert (
            len((await clients["B"].get(f"/api/v1/conversations/{cid}/messages")).json()["items"])
            == 1
        )
    finally:
        if process.poll() is None:
            process.terminate()
            await asyncio.to_thread(process.wait, 5)
