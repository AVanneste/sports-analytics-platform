"""Pinnacle's prices from the guest feed its website reads: the sharp reference for +EV alerts.

Pinnacle closed its public API in 2025; ``guest.api.arcadia.pinnacle.com`` still serves every
prematch board with the site's public key (``PINNACLE_KEY``). Two calls per sport: matchups (teams,
league, start) and straight markets (prices), joined on ``matchupId``. Prices are American odds.
Cloudflare 403s an IP after a handful of rapid requests, so callers should stay at a few calls per run.
"""
from typing import Dict, List

import requests

from sports_common.secrets import get_secret

BASE_URL = "https://guest.api.arcadia.pinnacle.com/0.1"
SOCCER, TENNIS, BASKETBALL, HOCKEY, VOLLEYBALL, HANDBALL = 29, 33, 4, 19, 34, 18  # sport ids
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                                       "Chrome/130 Safari/537.36", "Accept": "application/json"})


def pinnacle_get(path: str) -> list:
    """GET a feed path; raises on any non-200 (a 403 is Cloudflare rate limiting, not worth retrying)."""
    response = _SESSION.get(f"{BASE_URL}/{path}", headers={"X-API-Key": get_secret("PINNACLE_KEY") or ""}, timeout=90)
    response.raise_for_status()
    return response.json()


def american_to_decimal(price: float) -> float:
    return round(1 + (price / 100 if price > 0 else 100 / -price), 4)


def parse_board(matchups: List[Dict], markets: List[Dict]) -> List[Dict]:
    """One row per open price of a head-to-head matchup: moneyline (home/away/draw), spread and
    total (over/under) for the match (period 0) and first half/set (1), team totals (``side``).
    A child matchup is the same game counted in other ``units`` (tennis games, soccer corners or
    bookings): its rows carry the parent's id and names; the main matchup's units are None. Specials (outrights) are skipped."""
    games = {m["id"]: m for m in matchups if m.get("type") == "matchup" and len(m.get("participants") or []) == 2}
    rows = []
    for market in markets:
        game = games.get(market.get("matchupId"))
        if game is None or market.get("status") != "open":
            continue
        parent = games.get(game.get("parentId"), game)
        suffix = f" ({game.get('units')})" if parent is game else ""  # child listed without its parent
        teams = {p["alignment"]: p["name"].removesuffix(suffix) for p in parent["participants"]}
        limit = next((lim["amount"] for lim in market.get("limits") or [] if lim.get("type") == "maxRiskStake"), None)
        for price in market.get("prices") or []:
            league = parent["league"]["name"] if parent is not game else game["league"]["name"].removesuffix(suffix)
            rows.append({"sport": game["league"]["sport"]["name"], "league": league,
                         "event_id": game.get("parentId") or game["id"],
                         "units": game.get("units") if game.get("parentId") else None, "start": game["startTime"],
                         "home": teams.get("home"), "away": teams.get("away"),
                         "market": market["type"], "period": market.get("period", 0), "side": market.get("side"),
                         "line": price.get("points"), "selection": price["designation"],
                         "price": american_to_decimal(price["price"]), "limit": limit,
                         "alternate": bool(market.get("isAlternate"))})
    return rows


def fetch_board(sport_id: int) -> List[Dict]:
    """Every open prematch price for a sport (two requests)."""
    return parse_board(pinnacle_get(f"sports/{sport_id}/matchups"), pinnacle_get(f"sports/{sport_id}/markets/straight"))
