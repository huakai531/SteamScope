import asyncio
import os
from uuid import UUID

import pytest
from sqlalchemy import select, update

from steamscope_social.modules.privacy.models import PrivacySettings
from steamscope_social.modules.users.avatar_gc import reconcile
from steamscope_social.modules.users.avatars import LocalAvatarStorage, drain_avatar_deletions
from steamscope_social.modules.users.models import User
from tests.integration.test_players import players  # noqa: F401
from tests.integration.test_social import social  # noqa: F401
from tests.unit.test_visuals_avatars import synthetic_image

pytestmark = pytest.mark.integration


async def test_avatar_shared_dtos_and_connections_only_privacy(social):  # noqa: F811
    auth, c, a, ids, call, send = social
    url = (await upload(auth, c["A"])).json()["avatar_url"]
    request = await send()
    incoming = (await c["B"].get("/api/v1/connection-requests/incoming")).json()["items"]
    assert incoming[0]["person"]["avatar_url"] == url
    notifications = (await c["B"].get("/api/v1/notifications")).json()["items"]
    assert notifications[0]["person"]["avatar_url"] == url
    await call("B", f"/connection-requests/{request}/accept")
    assert (await c["B"].get("/api/v1/connections")).json()["items"][0]["avatar_url"] == url
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(
            update(PrivacySettings)
            .where(PrivacySettings.user_id.in_(ids.values()))
            .values(messaging="connections")
        )
        await db.execute(
            update(PrivacySettings)
            .where(PrivacySettings.user_id == ids["A"])
            .values(profile="connections")
        )
    assert (await c["B"].get(url)).status_code == 200
    assert (await c["C"].get(url)).status_code == 404
    conversation = await call("B", "/conversations/direct", body={"handle": a["A"]["handle"]})
    assert conversation.json()["person"]["avatar_url"] == url
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(
            update(PrivacySettings)
            .where(PrivacySettings.user_id == ids["A"])
            .values(profile="private")
        )
    assert (await c["B"].get(url)).status_code == 404
    assert (await c["B"].get("/api/v1/connections")).json()["items"][0]["avatar_url"] is None


async def upload(auth, client, data=None):
    return await client.post(
        "/api/v1/me/avatar",
        content=data or synthetic_image(),
        headers={**await auth.headers(client), "Content-Type": "image/png"},
    )


async def test_avatar_owner_privacy_replace_remove_and_delete(auth):
    owner, other, anonymous = await auth.client(), await auth.client(), await auth.client()
    account = await auth.login(owner)
    peer = await auth.login(other)
    assert (await anonymous.post("/api/v1/me/avatar", content=synthetic_image())).status_code == 401
    assert (await owner.post("/api/v1/me/avatar", content=synthetic_image())).status_code == 403
    response = await upload(auth, owner)
    assert response.status_code == 200
    url = response.json()["avatar_url"]
    image = await owner.get(url)
    assert image.status_code == 200 and image.headers["content-type"] == "image/webp"
    assert "no-store" in image.headers["cache-control"]
    assert image.headers["x-content-type-options"] == "nosniff"
    assert (await anonymous.get(url)).status_code == 401
    assert (await other.get(url)).status_code == 404
    assert (await other.delete(url, headers=await auth.headers(other))).status_code == 405
    assert (await other.get("/api/v1/me")).json()["avatar_url"] is None
    async with auth.resources.sessions() as db, db.begin():
        await db.execute(
            update(PrivacySettings)
            .where(PrivacySettings.user_id == UUID(account["id"]))
            .values(profile="public")
        )
    assert (await other.get(url)).status_code == 200
    view = (await other.get("/api/v1/users/" + account["handle"])).json()
    assert view["avatar_url"] == url
    assert (
        await other.post("/api/v1/blocks/" + account["handle"], headers=await auth.headers(other))
    ).status_code in {200, 204}
    assert (await other.get(url)).status_code == 404
    assert (await owner.get(url.replace(account["handle"], peer["handle"]))).status_code == 404
    assert (await upload(auth, owner, b"bad PNG")).status_code == 422
    assert (await owner.get("/api/v1/me")).json()["avatar_url"] == url
    second = (await upload(auth, owner)).json()["avatar_url"]
    assert second != url
    assert (await owner.get(url)).status_code == 404
    assert not (auth.config.avatar_storage_path / url.rsplit("/", 1)[1]).exists()
    assert (await owner.delete("/api/v1/me/avatar", headers=await auth.headers(owner))).json()[
        "avatar_url"
    ] is None
    assert not list(auth.config.avatar_storage_path.iterdir())
    await upload(auth, owner)
    deleted = await owner.request(
        "DELETE", "/api/v1/me", json={"confirmation": "DELETE"}, headers=await auth.headers(owner)
    )
    assert deleted.status_code == 204
    await drain_avatar_deletions(auth.resources, auth.config)
    assert not list(auth.config.avatar_storage_path.iterdir())


async def test_storage_failure_preserves_reference_and_cleanup_retries(auth, monkeypatch):
    owner = await auth.client()
    await auth.login(owner)
    first = (await upload(auth, owner)).json()["avatar_url"]
    original_put, original_delete = LocalAvatarStorage.put, LocalAvatarStorage.delete

    def fail(*args):
        raise OSError("synthetic storage failure")

    monkeypatch.setattr(LocalAvatarStorage, "put", fail)
    assert (await upload(auth, owner)).status_code == 503
    assert (await owner.get("/api/v1/me")).json()["avatar_url"] == first
    monkeypatch.setattr(LocalAvatarStorage, "put", original_put)
    monkeypatch.setattr(LocalAvatarStorage, "delete", fail)
    second = (await upload(auth, owner)).json()["avatar_url"]
    assert (await owner.get(second)).status_code == 200
    assert len(list(auth.config.avatar_storage_path.iterdir())) == 2
    monkeypatch.setattr(LocalAvatarStorage, "delete", original_delete)
    await drain_avatar_deletions(auth.resources, auth.config)
    assert len(list(auth.config.avatar_storage_path.iterdir())) == 1


async def test_concurrent_replacements_and_orphan_reconciliation(auth):
    owner = await auth.client()
    account = await auth.login(owner)
    results = await asyncio.gather(upload(auth, owner), upload(auth, owner))
    assert all(r.status_code == 200 for r in results)
    current = (await owner.get("/api/v1/me")).json()["avatar_url"]
    assert current in [r.json()["avatar_url"] for r in results]
    await drain_avatar_deletions(auth.resources, auth.config)
    assert len(list(auth.config.avatar_storage_path.iterdir())) == 1
    active = auth.config.avatar_storage_path / current.rsplit("/", 1)[1]
    old = auth.config.avatar_storage_path / ("f" * 32 + ".webp")
    fresh = auth.config.avatar_storage_path / ("e" * 32 + ".webp")
    old.write_bytes(b"orphan")
    fresh.write_bytes(b"recent in-flight")
    os.utime(old, (1, 1))
    os.utime(active, (1, 1))
    assert await reconcile(auth.resources, auth.config) == 1
    assert active.exists() and fresh.exists() and not old.exists()
    async with auth.resources.sessions() as db:
        assert (
            await db.scalar(select(User.avatar_key).where(User.id == UUID(account["id"])))
            == active.name
        )
