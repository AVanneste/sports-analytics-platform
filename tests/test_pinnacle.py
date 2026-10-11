from sports_common.pinnacle import american_to_decimal, parse_board

LEAGUE = {"name": "Belgium - Pro League", "sport": {"name": "Soccer"}}
MATCHUPS = [
    {"id": 1, "type": "matchup", "parentId": None, "league": LEAGUE, "startTime": "2026-10-12T18:45:00Z",
     "participants": [{"alignment": "home", "name": "Union SG"}, {"alignment": "away", "name": "Genk"}]},
    {"id": 2, "type": "matchup", "parentId": 1, "units": "Corners", "league": LEAGUE, "startTime": "2026-10-12T18:45:00Z",  # corners child
     "participants": [{"alignment": "home", "name": "Union SG (Corners)"}, {"alignment": "away", "name": "Genk (Corners)"}]},
]
MARKETS = [
    {"matchupId": 1, "type": "moneyline", "period": 0, "status": "open", "limits": [{"type": "maxRiskStake", "amount": 2000}],
     "prices": [{"designation": "home", "price": -120}, {"designation": "draw", "price": 260}, {"designation": "away", "price": 310}]},
    {"matchupId": 1, "type": "team_total", "period": 0, "side": "home", "status": "open", "limits": [],
     "prices": [{"designation": "over", "points": 1.5, "price": 105}, {"designation": "under", "points": 1.5, "price": -125}]},
    {"matchupId": 1, "type": "total", "period": 0, "status": "closed", "prices": [{"designation": "over", "points": 2.5, "price": 100}]},
    {"matchupId": 2, "type": "total", "period": 0, "status": "open", "prices": [{"designation": "over", "points": 9.5, "price": 100}]},
]


def test_american_to_decimal():
    assert american_to_decimal(150) == 2.5
    assert american_to_decimal(-200) == 1.5
    assert american_to_decimal(100) == 2.0


def test_parse_board_keeps_open_prices_and_folds_children_into_parent():
    rows = parse_board(MATCHUPS, MARKETS)
    assert len(rows) == 6  # 3 moneyline + 2 team total + corners over; closed market skipped
    corners = rows[-1]
    assert (corners["event_id"], corners["units"], corners["home"], corners["line"]) == (1, "Corners", "Union SG", 9.5)
    home = rows[0]
    assert (home["home"], home["away"], home["selection"], home["price"], home["limit"]) == ("Union SG", "Genk", "home", 1.8333, 2000)
    tt = [r for r in rows if r["market"] == "team_total"]
    assert {(r["side"], r["selection"], r["line"]) for r in tt} == {("home", "over", 1.5), ("home", "under", 1.5)}
    assert tt[0]["limit"] is None


def test_child_without_parent_takes_parent_id_and_plain_names():
    child = {"id": 5, "type": "matchup", "parentId": 4, "units": "Games", "league": LEAGUE, "startTime": "2026-10-12T10:00:00Z",
             "participants": [{"alignment": "home", "name": "Iga Swiatek (Games)"}, {"alignment": "away", "name": "Coco Gauff (Games)"}]}
    market = {"matchupId": 5, "type": "total", "period": 0, "status": "open", "prices": [{"designation": "over", "points": 21.5, "price": -110}]}
    row = parse_board([child], [market])[0]
    assert (row["event_id"], row["units"], row["home"], row["away"]) == (4, "Games", "Iga Swiatek", "Coco Gauff")
