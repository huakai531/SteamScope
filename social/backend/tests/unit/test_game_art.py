import pytest

from steamscope_social.modules.steam.visuals import game_visual


@pytest.mark.parametrize("appid", [0, -1, True, 2**32, "123"])
def test_invalid_appid_cannot_derive_any_art(appid):
    visual = game_visual(appid, "a" * 40)
    assert visual.icon_url is visual.thumbnail_url is visual.card_url is None
    assert visual.source == "unavailable"


def test_art_candidates_use_shared_appid_without_icon_or_provider_request():
    # Deliberately no icon metadata: art is independent and remains only a candidate.
    visual = game_visual(3576350, None)
    prefix = "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/3576350/"
    assert visual.card_url == prefix + "library_hero.jpg"
    assert visual.thumbnail_url == prefix + "header.jpg"
    assert visual.icon_url is None
    assert visual.source == "steam"
    assert game_visual(3576350, "invalid").card_url == visual.card_url
