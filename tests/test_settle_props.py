from sports_common.settle_props import player_line, settle_props

NAMES = ["MIN", "PTS", "FG", "3PT", "FT", "REB", "AST"]
GAME = {"event_id": "1", "sport": "Basketball", "start": "2026-11-10T00:00+00:00", "home": "Atlanta Hawks", "away": "Los Angeles Lakers",
        "players": {"onyeka okongwu": player_line(NAMES, ["30", "16", "6-11", "2-5", "2-4", "9", "3"]),
                    "jaren jackson jr": player_line(NAMES, ["35", "20", "7-15", "4-8", "2-2", "5", "2"])},
        "roster": {"onyeka okongwu", "jaren jackson jr", "corey kispert"}}


def alert(side, units, line, selection="over", price=1.9):
    return {"captured_at": "2026-11-09T20:00:00Z", "sport": "Basketball", "start": "2026-11-10T00:00:00Z", "home": "Atlanta Hawks",
            "away": "LA Lakers", "market": "player_prop", "period": 0, "units": units, "side": side, "line": line,
            "selection": selection, "book": "napoleon", "price": price}


def test_player_line_counts_stats_and_ignores_dnp():
    assert player_line(NAMES, ["30", "16", "6-11", "2-5", "2-4", "9", "3"]) == {"points": 16, "rebounds": 9, "assists": 3, "threes": 2, "pts+reb+ast": 28}
    assert player_line(NAMES, []) is None and player_line(NAMES, ["0", "0", "0-0", "0-0", "0-0", "0", "0"]) is None


def test_props_settle_win_loss_push_void_and_skip_unknowns():
    rows = settle_props([alert("onyeka okongwu", "points", 15.5), alert("onyeka okongwu", "pts+reb+ast", 28.0, "under"),
                         alert("onyeka okongwu", "rebounds", 9.5), alert("jaren jackson", "threes", 3.5),
                         alert("corey kispert", "points", 8.5), alert("nobody here", "points", 8.5)], [GAME])
    got = {(r["side"], r["units"], r["selection"]): (r["result"], r["pnl"], r["score_home"]) for r in rows}
    assert got[("onyeka okongwu", "points", "over")] == ("win", 0.9, 16)
    assert got[("onyeka okongwu", "pts+reb+ast", "under")] == ("push", 0.0, 28)
    assert got[("onyeka okongwu", "rebounds", "over")] == ("loss", -1.0, 9)
    assert got[("jaren jackson", "threes", "over")][0] == "win"                      # "Jackson" matches "Jackson Jr" uniquely
    assert got[("corey kispert", "points", "over")] == ("void", 0.0, None)           # on the roster, did not play
    assert len(rows) == 5                                                           # the unknown player is not settled
