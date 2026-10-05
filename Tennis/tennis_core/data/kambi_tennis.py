"""Belgian match-winner prices for tennis: Unibet.be and Bingoal (Kambi), Napoleon (Superbet).

Kambi's ATP, WTA and Grand Slam list views carry every listed singles match with its "Match Odds";
Superbet's offer API lists Napoleon's. A fixture's price is Napoleon's where Napoleon lists the
match, else the best of Unibet and Bingoal; the earlier price (The Odds API's European median) is
kept in ``reference_odds["eu"]``.
"""
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import requests

from sports_common.belgian_prices import choose_prices, price_label
from sports_common.kambi import OPERATORS, best_prices, kambi_get, outcome_price
from sports_common.superbet import TENNIS, events_by_date, parse_prices, split_match_name
from tennis_core.utils.helpers import strip_accents

logger = logging.getLogger(__name__)

LIST_PATHS = ("tennis/atp", "tennis/wta", "tennis/grand_slam")
NAPOLEON_FIELDS = {"p1_odds": (521, 1329, None), "p2_odds": (521, 1330, None)}  # Superbet Match Winner


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


def _oriented(event: Dict, fixture: Dict) -> Optional[Tuple[Dict[str, Dict[str, float]], bool]]:
    """(the event's books in the fixture's player order, whether the order was swapped), or None
    when it is another match."""
    if event.get("circuit") and fixture.get("circuit") != event["circuit"]:
        return None
    if not _same_day(event["start"], fixture.get("date")):
        return None
    if _same_player(event["p1_name"], fixture.get("p1_name")) and _same_player(event["p2_name"], fixture.get("p2_name")):
        return dict(event["books"]), False
    if _same_player(event["p1_name"], fixture.get("p2_name")) and _same_player(event["p2_name"], fixture.get("p1_name")):
        return {book: {"p1_odds": o.get("p2_odds"), "p2_odds": o.get("p1_odds")} for book, o in event["books"].items()}, True
    return None


def merge_belgian_prices(fixtures: List[Dict], events: List[Dict]) -> int:
    """Add each event's book prices to the fixture it is (either player order, in place) and
    reprice it from all its Belgian books, Napoleon first; returns how many."""
    priced = 0
    for event in events:
        if not {"p1_odds", "p2_odds"} <= set(best_prices(event["books"])):
            continue
        for f in fixtures:
            oriented = _oriented(event, f)
            if oriented is None:
                continue
            books, swapped = oriented
            reference = dict(f.get("reference_odds") or {})
            if f.get("p1_odds") and f.get("p2_odds") and not f.get("belgian_books") and "eu" not in reference:
                reference["eu"] = {"p1_odds": f["p1_odds"], "p2_odds": f["p2_odds"], "bookmaker": f.get("bookmaker")}
            books = {**(f.get("belgian_books") or {}), **books}
            prices, sources, better = choose_prices(books)
            f.update(prices)
            f.update({"reference_odds": reference, "belgian_books": books, "price_books": sources,
                      "better_elsewhere": better, "bookmaker": price_label(sources, "p1_odds")})
            if "napoleon" not in event["books"]:  # the closing-price archive is keyed by Kambi ids, in Kambi's order
                f["kambi_event_id"], f["kambi_swapped"] = event["event_id"], swapped
            priced += 1
            break
    return priced


def fetch_napoleon_prices(within_hours: float = 24 * 4, now: Optional[datetime] = None) -> List[Dict]:
    """Napoleon's match-winner prices for singles matches (any tour; pairing is by players)."""
    now = now or datetime.now(timezone.utc)
    out = []
    for e in events_by_date(now.replace(tzinfo=None), (now + timedelta(hours=within_hours)).replace(tzinfo=None), TENNIS):
        p1, p2 = split_match_name(e.get("matchName"))
        odds = parse_prices(e.get("odds") or [], NAPOLEON_FIELDS, (("p1_odds", "p2_odds"),))
        if p1 and p2 and "/" not in p1 and odds:
            out.append({"event_id": e["eventId"], "start": e.get("utcDate"), "circuit": None,
                        "p1_name": p1, "p2_name": p2, "books": {"napoleon": odds}})
    return out


def add_belgian_prices(fixtures: List[Dict]) -> List[Dict]:
    """Tennis fixtures priced at Napoleon, else the best of Unibet and Bingoal."""
    for name, fetch in (("Kambi", fetch_belgian_prices), ("Napoleon", fetch_napoleon_prices)):
        try:
            n = merge_belgian_prices(fixtures, fetch())
            logger.info(f"[{name}] Belgian prices on {n} of {len(fixtures)} tennis fixtures")
        except Exception as e:  # prices are optional: never lose the fixtures
            logger.warning(f"[{name}] tennis: {e}")
    return fixtures
