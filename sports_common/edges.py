"""+EV Belgian prices: each matched book price against Pinnacle's vig-free price for the same selection.

Pinnacle's board (sports_common/pinnacle.py) is grouped into complete markets (moneyline
home/draw/away, a total's over/under at one line, a spread's two sides) and de-vigged by the power
method; a Belgian price row (sports_common/belgian_board.py) of a matched event
(sports_common/matching.py) then has a fair probability and an EV.
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Tuple

from sports_common.betting import MAX_CREDIBLE_EV, devig_power, expected_value, kelly_fraction

MIN_EV = 0.02
MAX_ODDS = 6.0
WITHIN_HOURS = 36
# Pinnacle's max stake on the market: a low limit is a line Pinnacle itself does not trust yet.
MIN_LIMIT = {"Soccer": 250, "Tennis": 200, "Basketball": 200}
_FLIP = {"home": "away", "away": "home"}


def _market_key(row: Dict) -> Tuple:
    """One complete market: the spread's key is the home line, so both sides share it."""
    line = row.get("line")
    if row["market"] == "spread" and line is not None and row["selection"] == "away":
        line = -line
    return row["event_id"], row["market"], row["period"], row.get("units"), row.get("side"), line


def _selection_key(row: Dict) -> Tuple:
    return row["event_id"], row["market"], row["period"], row.get("units"), row.get("side"), row.get("line"), row["selection"]


def fair_prices(pinnacle_rows: Iterable[Dict]) -> Dict[Tuple, Dict]:
    """{selection key: {"prob", "limit", "price"}} from every complete Pinnacle market."""
    markets: Dict[Tuple, List[Dict]] = {}
    for row in pinnacle_rows:
        markets.setdefault(_market_key(row), []).append(row)
    fair = {}
    for key, rows in markets.items():
        expected = 3 if key[1] == "moneyline" and any(r["selection"] == "draw" for r in rows) else 2
        if len(rows) != expected or len({r["selection"] for r in rows}) != expected:
            continue
        probs = devig_power([r["price"] for r in rows])
        if probs is None:
            continue
        for row, prob in zip(rows, probs):
            fair[_selection_key(row)] = {"prob": float(prob), "limit": row.get("limit"), "price": row["price"]}
    return fair


def oriented(row: Dict, game_id, swapped: bool) -> Dict:
    """A book row re-keyed onto its Pinnacle game, home and away swapped back when the book lists
    them the other way round (a spread line belongs to its team, so it stays)."""
    out = {**row, "event_id": game_id}
    if swapped:
        out["selection"] = _FLIP.get(row["selection"], row["selection"])
        out["side"] = _FLIP.get(row.get("side"), row.get("side"))
    return out


def misread_markets(book_rows: Iterable[Dict]) -> set:
    """(book, market key) of book markets whose sides add up to under 100%: no book prices below
    a zero margin, so such a market was read wrongly (another market under a familiar name)."""
    implied: Dict[Tuple, float] = {}
    for row in book_rows:
        key = (row["book"], _market_key(row))
        implied[key] = implied.get(key, 0.0) + 1 / row["price"]
    return {key for key, total in implied.items() if total < 1.0}


def find_edges(book_rows: Iterable[Dict], matches: Dict[Tuple, Tuple], fair: Dict[Tuple, Dict], games: Dict,
               min_ev: float = MIN_EV, now: Optional[datetime] = None) -> List[Dict]:
    """Book prices with EV >= ``min_ev`` against Pinnacle, best first. ``games`` maps a Pinnacle
    event_id to its sport/league/start/home/away. Skipped: misread book markets, EV past MAX_CREDIBLE_EV (a mismatched
    market, not value), odds over MAX_ODDS, kick-off past WITHIN_HOURS, Pinnacle limit under MIN_LIMIT."""
    now = now or datetime.now(timezone.utc)
    book_rows = list(book_rows)
    misread = misread_markets(book_rows)
    edges = []
    for row in book_rows:
        match = matches.get((row["book"], row["event_id"]))
        if match is None or row["price"] > MAX_ODDS or (row["book"], _market_key(row)) in misread:
            continue
        game = games[match[0]]
        start = datetime.fromisoformat(str(game["start"]).replace("Z", "+00:00"))
        if not now < start <= now + timedelta(hours=WITHIN_HOURS):
            continue
        priced = oriented(row, *match)
        ref = fair.get(_selection_key(priced))
        if ref is None or (ref["limit"] or 0) < MIN_LIMIT.get(game["sport"], 250):
            continue
        ev = expected_value(ref["prob"], row["price"])
        if not min_ev <= ev < MAX_CREDIBLE_EV:
            continue
        edges.append({**priced, "sport": game["sport"], "league": game.get("league"), "start": game["start"],
                      "home": game["home"], "away": game["away"], "book_event_id": row["event_id"],
                      "fair_prob": ref["prob"], "fair_odds": round(1 / ref["prob"], 3), "pinnacle_price": ref["price"],
                      "limit": ref["limit"], "ev": ev, "stake": kelly_fraction(ref["prob"], row["price"])})
    return sorted(edges, key=lambda e: e["ev"], reverse=True)
