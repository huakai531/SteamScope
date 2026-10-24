from types import SimpleNamespace as Object

from steamscope_social.modules.social.discovery import rank


def view(*, stale=False, minutes=100, recent=10):
    games = [Object(app_id=i, total_minutes=minutes, recent_minutes=recent) for i in range(8)]
    return Object(
        games=games,
        profile=Object(
            handle="fixture",
            display_name="Fixture",
            library_state=Object(data_available=True, stale=stale),
            recent_state=Object(data_available=not stale),
            recent_games=games if not stale else [],
        ),
    )


def test_ranking_weights_caps_and_known_unknown_zero():
    maximum = rank(view(), view(), True)
    assert maximum.score == 100 and maximum.mutual_games == 8 and maximum.recent_overlap == 8
    assert rank(view(), view(), False).score == 90
    assert rank(view(minutes=None, recent=None), view(), False).score == 50
    assert rank(view(minutes=0, recent=0), view(), False).score == 50


def test_stale_history_not_used_even_when_owner_can_display_it():
    result = rank(view(stale=True), view(), False)
    assert result.score == 0 and result.mutual_games is None and result.recent_overlap is None
    friend_only = rank(view(stale=True), view(), True)
    assert friend_only.score == 10 and friend_only.reasons == [
        "Your Steam friend is also on SteamScope"
    ]
