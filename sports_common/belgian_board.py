"""Every Belgian book's prices for whole sports, keyed like Pinnacle's board (sports_common/pinnacle.py).

A price row is ``book, event_id, sport, league, start, home, away`` plus the market key Pinnacle
uses: ``market`` (moneyline, spread, total, team_total), ``period`` (0 match, 1 first half/set),
``units`` (None for the main score; "Corners", "Games"), ``side`` (team totals), ``line`` and
``selection`` (home/draw/away, over/under). Markets that Pinnacle does not price the same way
(combos, 3-way handicaps, second halves, cards, player props) are dropped, never guessed.

Kambi (Unibet, Bingoal): a sport's list view has every match with its main market; batched
``betoffer/event/{id,id,...}`` calls add the rest. Napoleon (Superbet): ``events/by-date`` has the
main market, ``events/{id}`` everything (about 1 MB a match, so callers pick which matches).
"""
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Tuple

import requests

from sports_common.kambi import OPERATORS, kambi_get, outcome_price
from sports_common.matching import player_key
from sports_common.superbet import event_details, events_by_date, split_match_name

logger = logging.getLogger(__name__)

KAMBI_SPORTS = {"Soccer": "football", "Tennis": "tennis", "Basketball": "basketball",  # Pinnacle name -> Kambi
                "Hockey": "ice_hockey", "Volleyball": "volleyball", "Handball": "handball"}
SUPERBET_SPORTS = {5: "Soccer", 2: "Tennis", 4: "Basketball", 3: "Hockey", 1: "Volleyball", 11: "Handball"}
REGULATION = 6  # Pinnacle's period for ice hockey's regular time (period 0 includes overtime and shootout)
_STAT = r"(goal|point|corner|game|set)s?\b"  # "Game Handicap" and "Total Games" alike
_UNITS = {"corner": "Corners", "game": "Games"}
_KAMBI_SELECTION = {"OT_ONE": "home", "OT_CROSS": "draw", "OT_TWO": "away", "OT_OVER": "over", "OT_UNDER": "under"}
_SUPERBET_SELECTION = {"1": "home", "X": "draw", "2": "away"}
# Exact names only: books also list "First to 100 Points" or "Next Corner" as 2-way "Match" offers.
_KAMBI_MONEYLINE = re.compile(r"(full time|half time|match odds|match|moneyline|most corners)"
                              r"( - (including overtime|regular time).*)?$", re.I)
_SUPERBET_MONEYLINE = re.compile(r"(full time|half time|match winner|winner|match betting( \(incl\. overtime\))?)$", re.I)


def _units(label: str) -> Optional[str]:
    match = re.search(_STAT, label, re.I)
    return _UNITS.get(match.group(1).lower()) if match else None


def _period(label: str) -> Optional[int]:
    """0 for the match (overtime included), 1 for the first half, REGULATION for ice hockey's regular
    time; None for anything else (2nd half, single sets, quarters, hockey periods...)."""
    low = label.lower()
    if "2nd half" in low or re.search(r"set \d|quarter|period \d", low):
        return None
    if "regular time" in low:
        return REGULATION
    return 1 if ("1st half" in low or low.startswith("half time")) else 0


def _with_sport(key: Optional[Dict], sport: str, label: str) -> Optional[Dict]:
    """Sport quirks: volleyball points are a side unit (its main score is sets, unlike basketball);
    Napoleon's ice hockey markets are regular time."""
    if key is None:
        return None
    if sport == "Volleyball" and "point" in label.lower():
        key = {**key, "units": "Points"}
    return key


def _side(label: str, home: str, away: str) -> Optional[str]:
    """Whose team total a label is: the team's full name as whole words ("AZ" not inside "Hazard")."""
    for side, name in (("home", home), ("away", away)):
        if name and re.search(rf"(?<!\w){re.escape(name.lower())}(?!\w)", label.lower()):
            return side
    return None


def kambi_market(label: str, offer_type: str, outcome_types: set, home: str, away: str) -> Optional[Dict]:
    """The market key of a Kambi bet offer (without line and selection), or None when it has no
    Pinnacle equivalent."""
    period = _period(label)
    plain = re.sub(r" - including overtime( and penalty shootout)?", "", label, flags=re.I)
    if period is None or re.search(r"card|booking|odd/even|&| and |draw no bet|double chance|player", plain, re.I):
        return None
    if (offer_type == "Match" and _KAMBI_MONEYLINE.match(label)
            and outcome_types in ({"OT_ONE", "OT_CROSS", "OT_TWO"}, {"OT_ONE", "OT_TWO"})):
        return {"market": "moneyline", "period": period, "units": _units(label), "side": None}
    if offer_type in ("Over/Under", "Asian Over/Under") and re.match(r"total " + _STAT, label, re.I):
        side = _side(label, home, away)
        return {"market": "team_total" if side else "total", "period": period, "units": _units(label), "side": side}
    if "Handicap" in offer_type and outcome_types == {"OT_ONE", "OT_TWO"} and re.search(r"handicap|spread|puck line", label, re.I):
        return {"market": "spread", "period": period, "units": _units(label), "side": None}
    return None


# Kambi's basketball player over/unders -> Pinnacle's stat names (sports_common.pinnacle.PROP_STATS)
KAMBI_PROPS = {"points scored by the player": "points", "rebounds by the player": "rebounds",
               "assists by the player": "assists", "3-point field goals made by the player": "threes",
               "points, rebounds & assists by the player": "pts+reb+ast"}


def kambi_prop(label: str, offer_type: str) -> Optional[str]:
    """The stat of a Kambi player over/under (overtime included, like Pinnacle's), or None."""
    if offer_type != "Player Occurrence Line":
        return None
    return KAMBI_PROPS.get(re.sub(r" - including overtime$", "", label.strip(), flags=re.I).lower())


def parse_kambi_event(event: Dict, offers: Iterable[Dict], book: str, sport: str) -> List[Dict]:
    """Price rows of one Kambi event from its bet offers."""
    home, away = event.get("homeName") or "", event.get("awayName") or ""
    base = {"book": book, "event_id": event["id"], "sport": sport, "league": event.get("group"),
            "start": event.get("start"), "home": home, "away": away}
    rows = []
    for offer in offers:
        outcomes = offer.get("outcomes") or []
        label = (offer.get("criterion") or {}).get("englishLabel") or (offer.get("criterion") or {}).get("label", "")
        stat = kambi_prop(label, (offer.get("betOfferType") or {}).get("englishName") or (offer.get("betOfferType") or {}).get("name", ""))
        if stat:
            priced = [(o, outcome_price(o)) for o in outcomes if o.get("type") in ("OT_OVER", "OT_UNDER")]
            players = {o.get("participant") for o, _ in priced}
            if len(priced) == 2 and len(players) == 1 and all(p for _, p in priced) and None not in players:
                rows += [{**base, "market": "player_prop", "period": 0, "units": stat, "side": player_key(o["participant"]),
                          "line": o["line"] / 1000 if o.get("line") is not None else None,
                          "selection": _KAMBI_SELECTION[o["type"]], "price": price} for o, price in priced]
            continue
        key = _with_sport(kambi_market(label, (offer.get("betOfferType") or {}).get("englishName")
                                       or (offer.get("betOfferType") or {}).get("name", ""),
                                       {o.get("type") for o in outcomes}, home, away), sport, label)
        if key is None:
            continue
        priced = [(o, outcome_price(o)) for o in outcomes]
        if any(price is None for _, price in priced):  # a market counts only with every side open
            continue
        for o, price in priced:
            line = o["line"] / 1000 if o.get("line") is not None else None
            rows.append({**base, **key, "line": line, "selection": _KAMBI_SELECTION[o["type"]], "price": price})
    return rows


def _upcoming(event: Dict, now: datetime, within_hours: float) -> bool:
    if event.get("state") not in (None, "NOT_STARTED") or not event.get("homeName") or not event.get("start"):
        return False
    if "esports" in str(event.get("path")).lower():
        return False
    start = datetime.fromisoformat(event["start"].replace("Z", "+00:00"))
    return now < start <= now + timedelta(hours=within_hours)


def fetch_kambi_board(sport: str, within_hours: float = 36, batch: int = 40, now: Optional[datetime] = None,
                      pause: float = 0.3) -> List[Dict]:
    """All markets of every upcoming match of a sport (Pinnacle's sport name) at Unibet and Bingoal:
    one list call plus one call per ``batch`` matches, per book."""
    now = now or datetime.now(timezone.utc)
    rows: List[Dict] = []
    for book, operator in OPERATORS.items():
        try:
            listed = kambi_get(operator, f"listView/{KAMBI_SPORTS[sport]}/all/all/all/matches.json").get("events") or []
        except (requests.RequestException, ValueError) as e:
            logger.warning(f"[Kambi] {book} {sport} list: {e}")
            continue
        events = {item["event"]["id"]: item["event"] for item in listed if _upcoming(item.get("event") or {}, now, within_hours)}
        ids = list(events)
        for i in range(0, len(ids), batch):
            chunk = ids[i:i + batch]
            time.sleep(pause)
            try:
                offers = kambi_get(operator, f"betoffer/event/{','.join(map(str, chunk))}.json").get("betOffers") or []
            except (requests.RequestException, ValueError) as e:
                logger.warning(f"[Kambi] {book} {sport} offers: {e}")
                continue
            by_event: Dict[int, List[Dict]] = {}
            for offer in offers:
                by_event.setdefault(offer.get("eventId"), []).append(offer)
            for event_id in chunk:
                rows += parse_kambi_event(events[event_id], by_event.get(event_id, []), book, sport)
    return rows


def superbet_market(name: str, home: str, away: str) -> Optional[Dict]:
    """The market key of a Superbet market name (without line and selection), or None."""
    period = _period(name)
    name = re.sub(r"^1st Half - ", "", name)
    if period is None or re.search(r"&| or |card|booking|multigoal|exact|correct|/", name, re.I):
        return None
    if _SUPERBET_MONEYLINE.match(name):
        return {"market": "moneyline", "period": 1 if name.lower().startswith("half time") else period,
                "units": None, "side": None}
    if re.match(r"(asian )?total " + _STAT, name, re.I) and "odd/even" not in name.lower():
        side = _side(name, home, away)
        return {"market": "team_total" if side else "total", "period": period, "units": _units(name), "side": side}
    if re.match(r"(asian )?(handicap|points? handicap|game handicap|set handicap|puck line)", name, re.I):
        return {"market": "spread", "period": period, "units": _units(name), "side": None}
    return None


# Napoleon's player over/unders ("Player - Total Points (incl. overtime)") -> Pinnacle's stat names
SUPERBET_PROPS = {"points": "points", "rebounds": "rebounds", "assists": "assists", "3 pointers made": "threes",
                  "points + rebounds + assists": "pts+reb+ast"}
_SUPERBET_PROP_MARKET = re.compile(r"^player - total (.+?) \(incl\. overtime\)$", re.I)
_SUPERBET_PROP_OUTCOME = re.compile(r"^(.+?), (.+?) - (over|under) ([\d.]+)$", re.I)


def superbet_props(odds: Iterable[Dict], base: Dict) -> List[Dict]:
    """Napoleon player over/unders: "Bonner, DeWanna - Over 8.5" in "Player - Total Points (incl.
    overtime)", kept when both sides of a player's line are open."""
    lines: Dict[Tuple, Dict[str, float]] = {}
    for o in odds:
        market = _SUPERBET_PROP_MARKET.match(o.get("marketName") or "")
        stat = SUPERBET_PROPS.get(market.group(1).lower()) if market else None
        outcome = _SUPERBET_PROP_OUTCOME.match(str(o.get("name") or "")) if stat else None
        if not outcome:
            continue
        last, first, side, line = outcome.groups()
        key = (stat, player_key(f"{first} {last}"), float(line))
        lines.setdefault(key, {})[side.lower()] = (round(float(o["price"]), 3)
                                                    if o.get("status") == "active" and o.get("price") else None)
    return [{**base, "market": "player_prop", "period": 0, "units": stat, "side": player, "line": line,
             "selection": sel, "price": price}
            for (stat, player, line), prices in lines.items() if set(prices) == {"over", "under"} and all(prices.values())
            for sel, price in prices.items()]


def parse_superbet_event(event: Dict, odds: Iterable[Dict]) -> List[Dict]:
    """Napoleon price rows of one Superbet event."""
    home, away = split_match_name(event.get("matchName"))
    sport = SUPERBET_SPORTS.get(event.get("sportId"))
    if not home or not away or not sport:
        return []
    base = {"book": "napoleon", "event_id": event["eventId"], "sport": sport, "league": event.get("tournamentId"),
            "start": event.get("utcDate"), "home": home, "away": away}
    odds = list(odds)
    markets: Dict[str, List[Dict]] = {}
    unparsed = set()  # e.g. "Draw (-1)": a 3-way handicap, which is not Pinnacle's 2-way spread
    for o in odds:
        key = _with_sport(superbet_market(o.get("marketName") or "", home, away), sport, o.get("marketName") or "")
        if key is None:
            continue
        if sport == "Hockey" and key["period"] == 0:
            key = {**key, "period": REGULATION}
        market_id = o.get("marketUuid") or o.get("marketId")
        name = str(o.get("name") or "")
        if key["market"] == "moneyline":
            selection, line = _SUPERBET_SELECTION.get(name), None
        elif key["market"] == "spread":  # "Verl (0.5)": that team's own line
            match = re.match(r"(.+) \(([-+]?[\d.]+)\)$", name)
            selection = _side(match.group(1), home, away) if match else None
            line = float(match.group(2)) if match else None
        else:  # "Over 2.5"
            match = re.match(r"(over|under) ([\d.]+)$", name, re.I)
            selection, line = (match.group(1).lower(), float(match.group(2))) if match else (None, None)
        if selection is None:
            unparsed.add(market_id)
            continue
        price = o.get("price") if o.get("status") == "active" else None
        markets.setdefault(market_id, []).append({**base, **key, "line": line, "selection": selection,
                                                  "price": round(float(price), 3) if price else None})
    rows = []
    for market_id, group in markets.items():
        if market_id in unparsed:
            continue
        by_line: Dict[Optional[float], List[Dict]] = {}
        for row in group:  # one market holds several lines; each counts only with every side open
            by_line.setdefault(abs(row["line"]) if row["line"] is not None else None, []).append(row)
        for line_rows in by_line.values():
            if len(line_rows) >= 2 and all(r["price"] for r in line_rows):
                rows += line_rows
    return rows + (superbet_props(odds, base) if sport == "Basketball" else [])


def fetch_superbet_list(within_hours: float = 36, now: Optional[datetime] = None) -> List[Dict]:
    """Napoleon's upcoming events of our sports (raw Superbet events: main market only)."""
    now = now or datetime.now(timezone.utc)
    start = now.replace(tzinfo=None)
    return [e for e in events_by_date(start, start + timedelta(hours=within_hours)) if e.get("sportId") in SUPERBET_SPORTS]


def fetch_superbet_details(events: Iterable[Dict], pause: float = 0.3) -> List[Dict]:
    """Every market of the given Superbet events (one ~1 MB call each)."""
    rows: List[Dict] = []
    for event in events:
        time.sleep(pause)
        try:
            rows += parse_superbet_event(event, event_details(event["eventId"]).get("odds") or [])
        except (requests.RequestException, ValueError) as e:
            logger.warning(f"[Napoleon] event {event.get('eventId')}: {e}")
    return rows
