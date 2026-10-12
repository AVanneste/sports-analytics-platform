"""Pinnacle's prices from the guest feed its website reads: the sharp reference for +EV alerts.

Pinnacle closed its public API in 2025; ``guest.api.arcadia.pinnacle.com`` still serves every
prematch board with the site's public key (``PINNACLE_KEY``). Two calls per sport: matchups (teams,
league, start) and straight markets (prices), joined on ``matchupId``. Prices are American odds.
Cloudflare 403s an IP after a handful of rapid requests, so callers should stay at a few calls per run.
"""
import time
from typing import Dict, List

import requests

from sports_common.matching import player_key
from sports_common.secrets import get_secret

BASE_URL = "https://guest.api.arcadia.pinnacle.com/0.1"
SOCCER, TENNIS, BASKETBALL, HOCKEY, VOLLEYBALL, HANDBALL = 29, 33, 4, 19, 34, 18  # sport ids
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                                       "Chrome/130 Safari/537.36", "Accept": "application/json"})


PAUSE = 1.0  # seconds between requests: Cloudflare 403s bursts (12 calls a run with six sports)


def pinnacle_get(path: str, retries: int = 1) -> list:
    """GET a feed path, spaced PAUSE apart; a 403 (Cloudflare rate limiting) or 5xx is retried once
    after a longer pause, then raised."""
    for attempt in range(retries + 1):
        time.sleep(PAUSE if attempt == 0 else 15)
        response = _SESSION.get(f"{BASE_URL}/{path}", headers={"X-API-Key": get_secret("PINNACLE_KEY") or ""}, timeout=90)
        if response.status_code not in (403, 429, 500, 502, 503, 504) or attempt == retries:
            response.raise_for_status()
            return response.json()
    return []


def american_to_decimal(price: float) -> float:
    return round(1 + (price / 100 if price > 0 else 100 / -price), 4)


# Pinnacle's player-prop descriptions ("Allisha Gray Total Points") -> our stat names
PROP_STATS = {"Total Points": "points", "Total Rebounds": "rebounds", "Total Assists": "assists",
              "Total Threes Made": "threes", "Total Pts & Rebs & Asts": "pts+reb+ast"}


def parse_props(matchups: List[Dict], markets: List[Dict], games: Dict[int, Dict]) -> List[Dict]:
    """Player over/unders (category "Player Props"): market ``player_prop``, the stat as ``units``,
    the player (``player_key``) as ``side``, on the game's event id (``parentId``)."""
    props = {}
    for m in matchups:
        special = m.get("special") or {}
        if m.get("type") != "special" or special.get("category") != "Player Props":
            continue
        stat = next((s for suffix, s in PROP_STATS.items() if special.get("description", "").endswith(" " + suffix)), None)
        names = {p["id"]: p["name"].lower() for p in m.get("participants") or []}
        if stat and set(names.values()) == {"over", "under"}:
            player = special["description"][: -len(next(k for k, v in PROP_STATS.items() if v == stat)) - 1]
            props[m["id"]] = (m, stat, player, names)
    rows = []
    for market in markets:
        found = props.get(market.get("matchupId"))
        if found is None or market.get("type") != "total" or market.get("status", "open") != "open":
            continue
        m, stat, player, names = found
        game = games.get(m.get("parentId"), {})
        teams = {p["alignment"]: p["name"] for p in game.get("participants") or []}
        limit = next((lim["amount"] for lim in market.get("limits") or [] if lim.get("type") == "maxRiskStake"), None)
        for price in market.get("prices") or []:
            selection = names.get(price.get("participantId"))
            if selection:
                rows.append({"sport": m["league"]["sport"]["name"], "league": m["league"]["name"],
                             "event_id": m.get("parentId") or m["id"], "units": stat, "start": m["startTime"],
                             "home": teams.get("home"), "away": teams.get("away"), "market": "player_prop",
                             "period": 0, "side": player_key(player), "line": price.get("points"),
                             "selection": selection, "price": american_to_decimal(price["price"]), "limit": limit,
                             "alternate": False})
    return rows


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
    return rows + parse_props(matchups, markets, games)


def fetch_board(sport_id: int) -> List[Dict]:
    """Every open prematch price for a sport (two requests)."""
    return parse_board(pinnacle_get(f"sports/{sport_id}/matchups"), pinnacle_get(f"sports/{sport_id}/markets/straight"))
