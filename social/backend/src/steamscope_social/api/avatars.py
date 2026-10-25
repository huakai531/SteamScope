import asyncio
import logging

from fastapi import APIRouter, Request, Response
from sqlalchemy.exc import SQLAlchemyError

from steamscope_social.api.account import account_view
from steamscope_social.core.database import utcnow
from steamscope_social.modules.auth.security import (
    AuthError,
    authenticated,
    config_for,
    resources_for,
)
from steamscope_social.modules.privacy.models import PrivacySettings
from steamscope_social.modules.social.policy import access
from steamscope_social.modules.social.service import verified_user
from steamscope_social.modules.users.avatars import (
    KEY,
    MAX_UPLOAD,
    MIME_FORMATS,
    drain_avatar_deletions,
    new_avatar_key,
    normalize_avatar,
    retire_avatar,
    storage_for,
)
from steamscope_social.modules.users.schemas import AccountView

router = APIRouter(prefix="/api/v1", tags=["Platform avatars"])
logger = logging.getLogger("steamscope_social.avatars")


async def clean_retired(request: Request) -> None:
    try:
        await drain_avatar_deletions(resources_for(request), config_for(request))
    except (SQLAlchemyError, OSError, TimeoutError):
        logger.warning("avatar_cleanup_pending")


@router.post(
    "/me/avatar",
    response_model=AccountView,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                mime: {"schema": {"type": "string", "format": "binary"}} for mime in MIME_FORMATS
            },
        }
    },
)
async def upload_avatar(request: Request) -> AccountView:
    """Owner/session + exact Origin/CSRF. Raw PNG/JPEG/WebP body, at most 5 MiB."""
    key: str | None = None
    try:
        async with authenticated(request, write=True) as actor:
            mime = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if (
                mime not in MIME_FORMATS
                or request.headers.get("content-encoding", "identity") != "identity"
            ):
                raise AuthError(415, "AVATAR_FORMAT_UNSUPPORTED")
            length = request.headers.get("content-length")
            if length and (not length.isdecimal() or len(length) > 10 or int(length) > MAX_UPLOAD):
                raise AuthError(413, "AVATAR_TOO_LARGE")
            data = bytearray()
            async with asyncio.timeout(15):
                async for chunk in request.stream():
                    if len(data) + len(chunk) > MAX_UPLOAD:
                        raise AuthError(413, "AVATAR_TOO_LARGE")
                    data.extend(chunk)
            normalized = await asyncio.to_thread(normalize_avatar, bytes(data), mime)
            key = new_avatar_key()
            try:
                await asyncio.to_thread(storage_for(config_for(request)).put, key, normalized)
            except (OSError, ValueError):
                raise AuthError(503, "AVATAR_STORAGE_UNAVAILABLE") from None
            await retire_avatar(actor.db, actor.user.avatar_key)
            actor.user.avatar_key = key
            actor.user.avatar_updated_at = actor.user.updated_at = utcnow()
            await actor.db.flush()
            result = await account_view(actor)
    except BaseException:
        if key:
            # A connection loss during COMMIT can be ambiguous. Never blindly unlink:
            # the outbox independently checks for a committed active reference.
            try:
                async with resources_for(request).sessions() as db, db.begin():
                    await retire_avatar(db, key)
            except (SQLAlchemyError, OSError, TimeoutError):
                logger.warning("avatar_orphan_reconciliation_needed")
            await clean_retired(request)
        raise
    await clean_retired(request)
    return result


@router.delete("/me/avatar", response_model=AccountView)
async def remove_avatar(request: Request) -> AccountView:
    async with authenticated(request, write=True) as actor:
        await retire_avatar(actor.db, actor.user.avatar_key)
        actor.user.avatar_key = None
        actor.user.avatar_updated_at = actor.user.updated_at = utcnow()
        result = await account_view(actor)
    await clean_retired(request)
    return result


@router.get(
    "/users/{handle}/avatar/{key}",
    response_class=Response,
    responses={
        200: {"content": {"image/webp": {"schema": {"type": "string", "format": "binary"}}}}
    },
)
async def image(request: Request, handle: str, key: str) -> Response:
    """Every read rechecks profile privacy and blocks. No public storage mount/cache."""
    async with authenticated(request) as actor:
        target = await verified_user(actor.db, handle)
        settings = await actor.db.get(PrivacySettings, target.id)
        policy = await access(actor.db, actor.user.id, target.id)
        if (
            not settings
            or not policy.permits(settings.profile)
            or not KEY.fullmatch(key)
            or target.avatar_key != key
        ):
            raise AuthError(404, "AVATAR_NOT_AVAILABLE")
        try:
            content = await asyncio.to_thread(storage_for(config_for(request)).read, key)
        except (OSError, ValueError):
            raise AuthError(404, "AVATAR_NOT_AVAILABLE") from None
    return Response(
        content,
        media_type="image/webp",
        headers={
            "Cache-Control": "no-store, private",
            "X-Content-Type-Options": "nosniff",
            "Cross-Origin-Resource-Policy": "same-origin",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )
