from datetime import datetime, timezone

from sports_common.betting import devig, devig_power
from sports_common.edges import fair_prices, find_edges

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
GAMES = {1: {"sport": "Soccer", "league": "Belgium - Pro League", "start": "2026-10-12T18:45:00Z", "home": "Union SG", "away": "Genk"}}


def test_devig_power_sums_to_one_and_shades_longshots():
    odds = [1.5, 4.2, 7.0]
    power, mult = devig_power(odds), devig(odds)
    assert abs(power.sum() - 1) < 1e-9
    assert power[2] < mult[2] and power[0] > mult[0]
    assert devig_power([1.0, 2.0]) is None


def pin(selection, price, market="moneyline", line=None, limit=1000):
    return {"event_id": 1, "market": market, "period": 0, "units": None, "side": None, "line": line,
            "selection": selection, "price": price, "limit": limit}


def book(selection, price, event_id="x", market="moneyline", line=None, name="napoleon"):
    return {"book": name, "event_id": event_id, "market": market, "period": 0, "units": None, "side": None,
            "line": line, "selection": selection, "price": price}


def test_find_edges_prices_against_vig_free_pinnacle():
    fair = fair_prices([pin("home", 2.0), pin("draw", 3.6), pin("away", 3.9),
                        pin("home", 1.95, "spread", -0.25), pin("away", 1.95, "spread", 0.25)])
    rows = [book("home", 2.2), book("draw", 3.3), book("away", 3.5),
            book("home", 2.1, market="spread", line=-0.25), book("away", 1.8, market="spread", line=0.25)]
    edges = find_edges(rows, {("napoleon", "x"): (1, False)}, fair, GAMES, now=NOW)
    assert [(e["market"], e["selection"], e["price"]) for e in edges] == [("moneyline", "home", 2.2), ("spread", "home", 2.1)]
    assert edges[0]["ev"] > 0.02 and edges[0]["home"] == "Union SG"


def test_find_edges_swaps_home_away_and_skips_misread_or_thin_markets():
    fair = fair_prices([pin("home", 1.9), pin("away", 1.9)])
    swapped = [book("home", 1.75, "s"), book("away", 2.1, "s")]  # the book lists Genk first: its "away" is Union SG
    edge, = find_edges(swapped, {("napoleon", "s"): (1, True)}, fair, GAMES, now=NOW)
    assert edge["selection"] == "home" and edge["price"] == 2.1
    misread = [book("home", 2.1, "m"), book("away", 2.1, "m")]  # 95% implied: not this market
    assert find_edges(misread, {("napoleon", "m"): (1, False)}, fair, GAMES, now=NOW) == []
    thin = fair_prices([pin("home", 1.9, limit=100), pin("away", 1.9, limit=100)])
    assert find_edges(swapped, {("napoleon", "s"): (1, True)}, thin, GAMES, now=NOW) == []
