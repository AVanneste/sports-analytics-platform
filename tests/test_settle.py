from sports_common.settle import scores, settle, settle_alerts

P = lambda t, h, a: {"type": t, "homeTeamScore": str(h), "awayTeamScore": str(a)}
SOCCER = {"periods": [P("RegularPeriod", 1, 0), P("RegularPeriod", 1, 1), P("Overtime", 0, 1)], "homeTeamCorners": 6, "awayTeamCorners": 3}
HOCKEY = {"periods": [P("regular_period", 2, 0), P("regular_period", 0, 1), P("regular_period", 0, 1), P("overtime", 0, 0), P("penalties", 0, 1)]}
TENNIS = {"periods": [P("FIRST_SET", 6, 4), P("SECOND_SET", 3, 6), P("THIRD_SET", 10, 8)]}
A = lambda **k: {"sport": "Soccer", "market": "moneyline", "period": 0, "units": None, "side": None, "line": None,
                 "selection": "home", "price": 2.0, **k}


def test_scores_by_sport_period_and_units():
    assert scores("Soccer", SOCCER, 0, None) == (2, 1)            # regular time only
    assert scores("Soccer", SOCCER, 1, None) == (1, 0)
    assert scores("Soccer", SOCCER, 0, "Corners") == (6, 3)
    assert scores("Hockey", HOCKEY, 6, None) == (2, 2)            # regulation
    assert scores("Hockey", HOCKEY, 0, None) == (2, 3)            # shootout: one goal to the winner
    assert scores("Tennis", TENNIS, 0, None) == (2, 1)            # sets
    assert scores("Tennis", TENNIS, 0, "Games") == (10, 10)       # match tie-break = one game
    assert scores("Tennis", {"periods": [P("FIRST_SET", 6, 4), P("SECOND_SET", 2, 1)]}, 0, None) is None  # retirement
    assert scores("Soccer", SOCCER, 0, "Bookings") is None


def test_settle_markets_and_quarter_lines():
    assert settle(A(), SOCCER)["result"] == "win" and settle(A(), SOCCER)["pnl"] == 1.0
    assert settle(A(selection="away"), SOCCER, swapped=True)["result"] == "win"        # swapped: the alert's away is the feed's home
    assert settle(A(sport="Hockey", period=6, selection="home"), HOCKEY)["result"] == "loss"   # 2-2 in regulation, 3-way
    assert settle(A(market="spread", line=-1.0), SOCCER)["result"] == "push"
    assert settle(A(market="spread", line=-0.75), SOCCER) == {"score_home": 2, "score_away": 1, "result": "half_win", "pnl": 0.5}
    assert settle(A(market="spread", line=-1.25), SOCCER)["pnl"] == -0.5
    assert settle(A(market="total", selection="over", line=2.5), SOCCER)["result"] == "win"
    assert settle(A(market="team_total", side="away", selection="under", line=1.5), SOCCER)["result"] == "win"
    assert settle(A(market="total", units="Corners", selection="under", line=9.5, price=1.8), SOCCER)["pnl"] == 0.8
    assert settle(A(market="player_prop", units="points", side="x", selection="over", line=9.5), SOCCER) is None


def test_settle_alerts_matches_names_either_way_round():
    events = [{"event_id": 1, "sport": "Soccer", "start": "2026-11-01T18:00:00Z", "home": "KRC Genk", "away": "Royale Union SG", "meta": SOCCER}]
    alert = A(captured_at="2026-11-01T12:00:00Z", start="2026-11-01T18:00:00Z", home="Union SG", away="Genk", book="napoleon")
    row, = settle_alerts([alert], events)
    assert (row["score_home"], row["score_away"], row["result"]) == (1, 2, "loss")
