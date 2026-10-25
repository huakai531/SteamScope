"""Opaque local avatar storage; serving authorization stays in the API, never the filesystem."""

import asyncio
import io
import logging
import os
import re
import warnings
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from steamscope_social.core.config import Settings
from steamscope_social.core.resources import Resources
from steamscope_social.modules.auth.security import AuthError
from steamscope_social.modules.users.models import AvatarDeletion, User

MAX_UPLOAD = 5 * 1024 * 1024
MAX_PIXELS = 16_000_000
MIME_FORMATS = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}
KEY = re.compile(r"[a-f0-9]{32}\.webp")
logger = logging.getLogger("steamscope_social.avatars")


def avatar_url(user: User) -> str | None:
    return f"/api/v1/users/{user.handle}/avatar/{user.avatar_key}" if user.avatar_key else None


def normalize_avatar(data: bytes, content_type: str) -> bytes:
    if len(data) > MAX_UPLOAD:
        raise AuthError(413, "AVATAR_TOO_LARGE")
    expected = MIME_FORMATS.get(content_type)
    if expected is None:
        raise AuthError(415, "AVATAR_FORMAT_UNSUPPORTED")
    try:
        # Reject obvious appended payloads instead of preserving a container polyglot.
        if expected == "PNG" and not data.endswith(b"\x00\x00\x00\x00IEND\xaeB`\x82"):
            raise ValueError
        if expected == "JPEG" and not data.endswith(b"\xff\xd9"):
            raise ValueError
        if expected == "WEBP" and (
            len(data) < 12
            or data[:4] != b"RIFF"
            or data[8:12] != b"WEBP"
            or int.from_bytes(data[4:8], "little") + 8 != len(data)
        ):
            raise ValueError
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=[expected]) as image:
                if image.format != expected or getattr(image, "n_frames", 1) != 1:
                    raise ValueError
                if image.width * image.height > MAX_PIXELS or max(image.size) > 8192:
                    raise AuthError(422, "AVATAR_DIMENSIONS_EXCEEDED")
                image.verify()
            with Image.open(io.BytesIO(data), formats=[expected]) as image:
                image.load()
                pixels = ImageOps.fit(ImageOps.exif_transpose(image).convert("RGB"), (256, 256))
                # Fresh pixel-only image cannot carry EXIF/GPS, ICC, XMP or client metadata.
                clean = Image.new("RGB", (256, 256))
                clean.paste(pixels)
                output = io.BytesIO()
                clean.save(output, format="WEBP", quality=85, method=4)
                return output.getvalue()
    except AuthError:
        raise
    except (
        ValueError,
        SyntaxError,
        OSError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise AuthError(422, "AVATAR_IMAGE_INVALID") from None


class AvatarStorage(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def read(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalAvatarStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def path(self, key: str) -> Path:
        if not KEY.fullmatch(key):
            raise ValueError("Invalid storage key")
        candidate = self.root / key
        if candidate.is_symlink() or candidate.resolve().parent != self.root:
            raise ValueError("Invalid storage path")
        return candidate

    def put(self, key: str, data: bytes) -> None:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.path(key)
        created = False
        try:
            with path.open("xb") as output:
                created = True
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
        except BaseException:
            if created:
                path.unlink(missing_ok=True)
            raise

    def read(self, key: str) -> bytes:
        with self.path(key).open("rb") as image:
            data = image.read(262145)
        if len(data) > 262144:
            raise OSError("Avatar output exceeds bound")
        return data

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)


def storage_for(config: Settings) -> AvatarStorage:
    return LocalAvatarStorage(config.avatar_storage_path)


def new_avatar_key() -> str:
    return uuid4().hex + ".webp"


async def retire_avatar(db: AsyncSession, key: str | None) -> None:
    if key:
        await db.execute(insert(AvatarDeletion).values(key=key).on_conflict_do_nothing())


async def drain_avatar_deletions(resources: Resources, config: Settings) -> None:
    """Bounded retryable outbox. Active references are an independent deletion guard."""
    store = storage_for(config)
    async with resources.sessions() as db, db.begin():
        rows = list(
            await db.scalars(
                select(AvatarDeletion)
                .order_by(AvatarDeletion.created_at)
                .limit(20)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            if await db.scalar(select(User.id).where(User.avatar_key == row.key)):
                await db.delete(row)
                continue
            try:
                await asyncio.to_thread(store.delete, row.key)
            except (OSError, ValueError):
                logger.warning("avatar_cleanup_pending")
                continue
            await db.delete(row)
