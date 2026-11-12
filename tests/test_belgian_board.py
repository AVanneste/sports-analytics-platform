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


def test_napoleon_hockey_overtime_markets_are_not_regulation():
    from sports_common.belgian_board import REGULATION
    event = {"eventId": 3, "matchName": "Montreal Canadiens·Minnesota Wild", "sportId": 3, "utcDate": "2026-11-10T00:00:00Z", "tournamentId": 1}
    o = lambda market, name, price: {"marketName": market, "name": name, "price": price, "status": "active", "marketUuid": market}
    rows = parse_superbet_event(event, [
        o("Total Goals (incl. overtime and penalties)", "Over 6.5", 2.0), o("Total Goals (incl. overtime and penalties)", "Under 6.5", 1.8),
        o("Winner (incl. overtime and penalties)", "1", 2.02), o("Winner (incl. overtime and penalties)", "2", 1.8),
        o("Full Time", "1", 2.65), o("Full Time", "X", 4.0), o("Full Time", "2", 2.3)])
    periods = {(r["market"], r["selection"]): r["period"] for r in rows}
    assert periods[("total", "under")] == 0 and periods[("moneyline", "draw")] == REGULATION
    assert sorted(r["period"] for r in rows if r["market"] == "moneyline") == [0, 0, REGULATION, REGULATION, REGULATION]


def test_superbet_winner_names_of_every_sport_are_moneylines():
    for name in ("To Win the Match (incl. overtime)", "Moneyline (incl. overtime)", "Winner (incl. overtime)",
                 "Winner (incl. super over)", "Winner", "Match Winner", "Full Time"):
        assert superbet_market(name, "A", "B")["market"] == "moneyline", name
    for name in ("Map 1 - Winner", "Set 1 - Leg X - Winner", "Total legs", "Leg handicap"):  # per map / leg units: not compared
        assert superbet_market(name, "A", "B") is None, name
    assert superbet_market("Handicap (incl. overtime)", "A", "B")["market"] == "spread"
    assert superbet_market("Total Points (incl. overtime)", "A", "B") == {"market": "total", "period": 0, "units": None, "side": None}


def test_parse_altenar_main_markets():
    from sports_common.belgian_board import parse_altenar
    payload = {"events": [{"id": 7, "competitorIds": [1, 2], "champId": 9, "startDate": "2026-11-12T18:00:00Z", "marketIds": [10, 11, 12, 13]}],
               "competitors": [{"id": 1, "name": "Anyang Halla"}, {"id": 2, "name": "Yokohama Grits"}], "champs": [{"id": 9, "name": "Asia League"}],
               "markets": [{"id": 10, "typeId": 1, "oddIds": [1, 2, 3]}, {"id": 11, "typeId": 410, "oddIds": [4, 5]},
                           {"id": 12, "typeId": 412, "oddIds": [6, 7]}, {"id": 13, "typeId": 8, "oddIds": [8]}],
               "odds": [{"id": 1, "name": "1", "price": 2.1, "oddStatus": 0}, {"id": 2, "name": "Draw", "price": 4.0, "oddStatus": 0},
                        {"id": 3, "name": "2", "price": 2.9, "oddStatus": 0}, {"id": 4, "name": "1 (+1.5)", "price": 1.6667, "oddStatus": 0},
                        {"id": 5, "name": "2 (-1.5)", "price": 2.0, "oddStatus": 0}, {"id": 6, "name": "Over 5.5", "price": 1.9, "oddStatus": 0},
                        {"id": 7, "name": "Under 5.5", "price": 1.8, "oddStatus": 1}, {"id": 8, "name": "1", "price": 1.5, "oddStatus": 0}]}
    rows = parse_altenar(payload, "Hockey")
    got = {(r["market"], r["period"], r["selection"], r["line"], r["price"]) for r in rows}
    assert got == {("moneyline", 6, "home", None, 2.1), ("moneyline", 6, "draw", None, 4.0), ("moneyline", 6, "away", None, 2.9),
                   ("spread", 0, "home", 1.5, 1.667), ("spread", 0, "away", -1.5, 2.0)}   # suspended under: no total
    assert rows[0]["home"] == "Anyang Halla" and rows[0]["league"] == "Asia League" and rows[0]["book"] == "goldenpalace"


def test_parse_eurobet_winners_and_totals():
    from sports_common.belgian_board import parse_eurobet
    odd = lambda d, v: {"oddDescription": d, "oddValue": v}
    item = lambda desc, groups: {"eventInfo": {"eventDescription": desc, "eventData": 1794486600000, "programCode": 1, "eventCode": 2,
                                               "meetingDescription": "NFL"}, "betGroupList": [{"oddGroupList": groups}]}
    payload = {"result": {"dataGroupList": [{"itemList": [item("New York Giants - Washington Commanders", [
        {"oddGroupDescription": "FACE À FACE", "oddList": [odd("1", 242), odd("2", 150)]},
        {"oddGroupDescription": "1X2", "oddList": [odd("1", 249), odd("X", 1700), odd("2", 153)]},          # 3-way regular time: left out
        {"oddGroupDescription": "PLUS/MOINS DE (PROL. INCL.) 43.5", "oddList": [odd("Plus ", 185), odd("Moins ", 172)]},
        {"oddGroupDescription": "PLUS/MOINS DE 180'S 1.5", "oddList": [odd("Plus", 270), odd("Moins", 137)]}])]}]}}
    rows = parse_eurobet(payload, "Football")
    assert {(r["market"], r["selection"], r["line"], r["price"]) for r in rows} == {
        ("moneyline", "home", None, 2.42), ("moneyline", "away", None, 1.5), ("total", "over", 43.5, 1.85), ("total", "under", 43.5, 1.72)}
    assert rows[0]["start"] == "2026-11-12T12:30:00Z" and rows[0]["away"] == "Washington Commanders"
