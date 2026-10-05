"""Belgian match-winner prices for tennis (Unibet.be, Bingoal) from Kambi's public feed.

The ATP, WTA and Grand Slam list views carry every listed singles match with its "Match Odds".
The best Belgian price per player replaces the fixture's price (bets are placed at Belgian books);
the earlier price (The Odds API's European median) is kept in ``reference_odds["eu"]``.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests

from sports_common.kambi import OPERATORS, best_prices, kambi_get, outcome_price
from tennis_core.utils.helpers import strip_accents

logger = logging.getLogger(__name__)

LIST_PATHS = ("tennis/atp", "tennis/wta", "tennis/grand_slam")
BOOKMAKER_LABEL = "Best Belgian price (Unibet, Bingoal)"


def _circuit(event: Dict, path: str) -> Optional[str]:
    if path == "tennis/atp":
        return "ATP"
    if path == "tennis/wta":
        return "WTA"
    names = " ".join(str(p.get("termKey") or p.get("name") or "") for p in event.get("path") or []).lower()
    return "WTA" if "women" in names else "ATP"


def parse_list_view(payload: Dict, path: str) -> List[Dict]:
    """Upcoming singles matches with both players' prices."""
    matches = []
    for item in payload.get("events") or []:
        event = item.get("event") or {}
        if event.get("state") not in (None, "NOT_STARTED") or "/" in str(event.get("homeName")):  # doubles: "A/B"
            continue
        offer = next((b for b in item.get("betOffers") or []
                      if (b.get("criterion") or {}).get("label") == "Match Odds"), None)
        if not offer:
            continue
        by_type = {o.get("type"): o for o in offer.get("outcomes") or []}
        p1, p2 = outcome_price(by_type.get("OT_ONE", {})), outcome_price(by_type.get("OT_TWO", {}))
        if p1 and p2:
            matches.append({"event_id": event["id"], "start": event["start"], "circuit": _circuit(event, path),
                            "p1_name": event["homeName"], "p2_name": event["awayName"],
                            "odds": {"p1_odds": p1, "p2_odds": p2}})
    return matches


def fetch_belgian_prices() -> List[Dict]:
    """Every listed singles match with each book's prices: {event_id, start, circuit, p1_name, p2_name, books}."""
    events: Dict[int, Dict] = {}
    for book, operator in OPERATORS.items():
        for path in LIST_PATHS:
            try:
                listed = parse_list_view(kambi_get(operator, f"listView/{path}.json"), path)
            except (requests.RequestException, ValueError) as e:
                logger.warning(f"[Kambi] {book} {path}: {e}")
                continue
            for m in listed:
                events.setdefault(m["event_id"], {k: v for k, v in m.items() if k != "odds"} | {"books": {}})["books"][book] = m["odds"]
    return list(events.values())


def _tokens(name: str) -> set:
    return {w for w in re.sub(r"[^a-z ]", " ", strip_accents(str(name)).replace("-", " ")).split() if len(w) > 1}


def _same_player(a: str, b: str) -> bool:
    """Full names from two providers ("Alex De Minaur" / "Alex de Minaur", "Qinwen Zheng" / "Zheng Qinwen")."""
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta and tb) and (ta <= tb or tb <= ta or len(ta & tb) >= 2)


def _same_day(kickoff_utc: str, fixture_date) -> bool:
    try:
        day = datetime.fromisoformat(str(kickoff_utc).replace("Z", "+00:00")).astimezone(timezone.utc).date()
        return abs((day - datetime.fromisoformat(str(fixture_date)[:10]).date()).days) <= 1
    except ValueError:
        return False


def merge_belgian_prices(fixtures: List[Dict], events: List[Dict]) -> int:
    """Put the best Belgian prices on matching fixtures (in place, either player order); returns how many."""
    priced = 0
    for event in events:
        best = best_prices(event["books"])
        if not {"p1_odds", "p2_odds"} <= set(best):
            continue
        for f in fixtures:
            if f.get("circuit") != event["circuit"] or not _same_day(event["start"], f.get("date")):
                continue
            if _same_player(event["p1_name"], f.get("p1_name")) and _same_player(event["p2_name"], f.get("p2_name")):
                p1, p2 = best["p1_odds"], best["p2_odds"]
            elif _same_player(event["p1_name"], f.get("p2_name")) and _same_player(event["p2_name"], f.get("p1_name")):
                p1, p2 = best["p2_odds"], best["p1_odds"]
            else:
                continue
            reference = dict(f.get("reference_odds") or {})
            if f.get("p1_odds") and f.get("p2_odds") and "eu" not in reference:
                reference["eu"] = {"p1_odds": f["p1_odds"], "p2_odds": f["p2_odds"], "bookmaker": f.get("bookmaker")}
            f.update({"p1_odds": p1, "p2_odds": p2, "reference_odds": reference, "bookmaker": BOOKMAKER_LABEL,
                      "kambi_event_id": event["event_id"]})
            priced += 1
            break
    return priced


def add_belgian_prices(fixtures: List[Dict]) -> List[Dict]:
    """Tennis fixtures with the best Belgian price wherever Unibet or Bingoal list the match."""
    try:
        n = merge_belgian_prices(fixtures, fetch_belgian_prices())
        logger.info(f"[Kambi] Belgian prices on {n} of {len(fixtures)} tennis fixtures")
    except Exception as e:  # prices are optional: never lose the fixtures
        logger.warning(f"[Kambi] tennis: {e}")
    return fixtures
