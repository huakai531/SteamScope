import io

import pytest
from PIL import Image, PngImagePlugin

from steamscope_social.modules.auth.security import AuthError
from steamscope_social.modules.steam.client import map_response
from steamscope_social.modules.steam.visuals import game_visual
from steamscope_social.modules.users.avatars import MAX_UPLOAD, LocalAvatarStorage, normalize_avatar


def synthetic_image(format="PNG", size=(64, 48)):
    stream = io.BytesIO()
    image = Image.new("RGB", size, (32, 78, 128))
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("private-test-metadata", "must not survive")
    image.save(stream, format=format, pnginfo=metadata)
    return stream.getvalue()


@pytest.mark.parametrize(
    "format,mime", [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")]
)
def test_normalize_valid_synthetic_images(format, mime):
    output = normalize_avatar(synthetic_image(format), mime)
    with Image.open(io.BytesIO(output)) as image:
        assert image.format == "WEBP" and image.size == (256, 256)
        assert not image.getexif() and not image.info.get("xmp")
        assert "private-test-metadata" not in image.info
    assert b"must not survive" not in output


@pytest.mark.parametrize(
    "data,mime,status",
    [
        (b"x" * (MAX_UPLOAD + 1), "image/png", 413),
        (b"<svg/>", "image/svg+xml", 415),
        (b"<script>alert(1)</script>", "image/png", 422),
        (synthetic_image() + b"<script/>", "image/png", 422),
        (synthetic_image(), "image/jpeg", 422),
        (synthetic_image()[:40], "image/png", 422),
        (b"GIF89a", "image/gif", 415),
    ],
    ids=["size", "svg", "script", "appended-payload", "mime-mismatch", "truncated", "gif"],
)
def test_reject_unsafe_uploads(data, mime, status):
    with pytest.raises(AuthError) as error:
        normalize_avatar(data, mime)
    assert error.value.status == status


def test_reject_animation_and_excessive_dimensions():
    stream = io.BytesIO()
    Image.new("RGB", (16, 16), "red").save(
        stream, format="PNG", save_all=True, append_images=[Image.new("RGB", (16, 16), "blue")]
    )
    with pytest.raises(AuthError):
        normalize_avatar(stream.getvalue(), "image/png")
    with pytest.raises(AuthError) as error:
        normalize_avatar(synthetic_image(size=(8193, 1)), "image/png")
    assert error.value.code == "AVATAR_DIMENSIONS_EXCEEDED"


def test_storage_path_rejection_and_exclusive_create(tmp_path):
    storage = LocalAvatarStorage(tmp_path)
    key = "a" * 32 + ".webp"
    storage.put(key, b"first")
    with pytest.raises(FileExistsError):
        storage.put(key, b"second")
    assert storage.read(key) == b"first"
    for bad in ["../a.webp", "/tmp/a.webp", "C:\\evil.webp", "a.svg"]:
        with pytest.raises(ValueError):
            storage.read(bad)
    storage.delete(key)
    storage.delete(key)


@pytest.mark.parametrize(
    "appid,hashed",
    [
        (0, "a" * 40),
        (True, "a" * 40),
        (2**32, "a" * 40),
        (1, None),
        (1, "https://evil.example/a"),
        (1, "a" * 41),
    ],
)
def test_game_visual_invalid_is_absent(appid, hashed):
    assert game_visual(appid, hashed).icon_url is None


def test_canonical_visual_normalizes_hash_and_optional_metadata_does_not_fail_library():
    assert (
        game_visual(123, "A" * 40).icon_url
        == "https://media.steampowered.com/steamcommunity/public/images/apps/123/"
        + "a" * 40
        + ".jpg"
    )
    for value in [None, 123, {}, "x" * 1000, "<script>"]:
        result = map_response(
            "library",
            {
                "response": {
                    "game_count": 1,
                    "games": [{"appid": 123, "playtime_forever": 456, "img_icon_url": value}],
                }
            },
            "76561198000000001",
        )
        assert result.status == "populated"
        assert result.games[0].icon_hash is None and result.games[0].total_minutes == 456
