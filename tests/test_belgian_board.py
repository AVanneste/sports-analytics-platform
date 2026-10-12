from sports_common.belgian_board import kambi_market, parse_kambi_event, parse_superbet_event, superbet_market


def test_kambi_market_keys():
    m = lambda label, kind, types: kambi_market(label, kind, set(types), "Union SG", "Genk")
    assert m("Full Time", "Match", ["OT_ONE", "OT_CROSS", "OT_TWO"]) == {"market": "moneyline", "period": 0, "units": None, "side": None}
    assert m("Half Time", "Match", ["OT_ONE", "OT_CROSS", "OT_TWO"])["period"] == 1
    assert m("Total Goals by Genk", "Over/Under", ["OT_OVER", "OT_UNDER"])["side"] == "away"
    assert m("Total Corners", "Over/Under", ["OT_OVER", "OT_UNDER"])["units"] == "Corners"
    assert m("Total Games", "Over/Under", ["OT_OVER", "OT_UNDER"])["units"] == "Games"
    assert m("Game Handicap", "Handicap", ["OT_ONE", "OT_TWO"])["units"] == "Games"
    assert m("Set Handicap", "Handicap", ["OT_ONE", "OT_TWO"])["units"] is None
    assert m("Handicap", "Handicap", ["OT_ONE", "OT_TWO"])["market"] == "spread"
    assert m("Moneyline - Including Overtime", "Match", ["OT_ONE", "OT_TWO"])["market"] == "moneyline"
    assert m("Most Corners", "Match", ["OT_ONE", "OT_CROSS", "OT_TWO"])["units"] == "Corners"
    assert m("First to 100 Points - Including Overtime", "Match", ["OT_ONE", "OT_TWO"]) is None
    assert m("Next Corner, No Corner No Bet (1)", "Match", ["OT_ONE", "OT_TWO"]) is None
    assert m("3-Way Handicap", "Handicap", ["OT_ONE", "OT_CROSS", "OT_TWO"]) is None
    assert m("Total Goals - 2nd Half", "Over/Under", ["OT_OVER", "OT_UNDER"]) is None
    assert m("Total Cards", "Over/Under", ["OT_OVER", "OT_UNDER"]) is None
    assert m("Union SG to Win and Both Teams To Score", "Yes/No", ["OT_YES", "OT_NO"]) is None


def test_parse_kambi_event_needs_every_side_open():
    event = {"id": 7, "homeName": "Union SG", "awayName": "Genk", "start": "2026-10-12T18:45:00Z", "group": "Pro League"}
    over_under = lambda status: {"criterion": {"label": "Total Goals"}, "betOfferType": {"name": "Over/Under"}, "outcomes": [
        {"type": "OT_OVER", "odds": 1900, "line": 2500}, {"type": "OT_UNDER", "odds": 1950, "line": 2500, "status": status}]}
    rows = parse_kambi_event(event, [over_under("OPEN")], "unibet", "Soccer")
    assert [(r["selection"], r["line"], r["price"]) for r in rows] == [("over", 2.5, 1.9), ("under", 2.5, 1.95)]
    assert parse_kambi_event(event, [over_under("SUSPENDED")], "unibet", "Soccer") == []


def test_superbet_market_keys():
    m = lambda name: superbet_market(name, "Union SG", "Genk")
    assert m("Full Time")["market"] == "moneyline"
    assert m("Match betting (incl. overtime)")["market"] == "moneyline"
    assert m("Winner of the 1st set") is None
    assert m("1st Half - Total Goals") == {"market": "total", "period": 1, "units": None, "side": None}
    assert m("Total Corners Genk") == {"market": "team_total", "period": 0, "units": "Corners", "side": "away"}
    assert m("Asian Handicap")["market"] == "spread"
    for name in ("2nd Half - Total Goals", "Total Goals & Both Teams to Score", "Correct Score", "Half Time/Full Time"):
        assert m(name) is None


def test_parse_superbet_event_lines_and_3way_handicap():
    event = {"eventId": 9, "matchName": "Union SG·Genk", "sportId": 5, "utcDate": "2026-10-12T18:45:00Z", "tournamentId": 324}
    o = lambda market, name, price, mid, status="active": {"marketName": market, "name": name, "price": price,
                                                           "marketUuid": mid, "status": status}
    odds = [o("Handicap", "Union SG (-0.5)", 1.9, "h"), o("Handicap", "Genk (0.5)", 1.95, "h"),
            o("Total Goals", "Over 2.5", 1.8, "t"), o("Total Goals", "Under 2.5", 2.0, "t"),
            o("Total Goals", "Over 3.5", 3.0, "t"), o("Total Goals", "Under 3.5", 1.3, "t", status="inactive"),
            o("Handicap", "Union SG (-1)", 2.5, "h3"), o("Handicap", "Draw (-1)", 3.4, "h3"), o("Handicap", "Genk (1)", 2.6, "h3")]
    rows = parse_superbet_event(event, odds)
    got = {(r["market"], r["selection"], r["line"], r["price"]) for r in rows}
    assert got == {("spread", "home", -0.5, 1.9), ("spread", "away", 0.5, 1.95),
                   ("total", "over", 2.5, 1.8), ("total", "under", 2.5, 2.0)}  # 3.5 half-suspended, 3-way voided


def test_new_sports_timing_and_units():
    from sports_common.belgian_board import REGULATION, _with_sport
    m = lambda label, kind, types: kambi_market(label, kind, set(types), "Anaheim Ducks", "Utah")
    full = m("Moneyline - Including Overtime and penalty shootout", "Match", ["OT_ONE", "OT_TWO"])
    assert (full["market"], full["period"]) == ("moneyline", 0)
    assert m("Match Odds - Regular Time", "Match", ["OT_ONE", "OT_CROSS", "OT_TWO"])["period"] == REGULATION
    assert m("Puck Line - Regular Time", "Handicap", ["OT_ONE", "OT_TWO"]) == {"market": "spread", "period": REGULATION, "units": None, "side": None}
    assert m("Total Goals - Period 1", "Over/Under", ["OT_OVER", "OT_UNDER"]) is None
    point = _with_sport(superbet_market("Point handicap", "A", "B"), "Volleyball", "Point handicap")
    assert point["units"] == "Points" and _with_sport(superbet_market("Set handicap", "A", "B"), "Volleyball", "Set handicap")["units"] is None
    assert _with_sport(superbet_market("Total Points", "A", "B"), "Basketball", "Total Points")["units"] is None
