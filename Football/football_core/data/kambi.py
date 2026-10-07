"""Belgian bookmaker prices: Unibet.be and Bingoal from Kambi's public feed, Napoleon from Superbet's.

Both books run on Kambi (see sports_common/kambi.py). A league's list view carries 1X2 and
Over/Under 2.5 for every match; one call per match adds BTTS and the corners lines.

A fixture's price per selection is Napoleon's where Napoleon lists it, else the best of Unibet and
Bingoal (bets are placed at Belgian books, mostly Napoleon); all books' prices stay in
``belgian_books`` and the price the fixture had before in ``reference_odds["eu"]``.
"""
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

import requests

from football_core.utils.helpers import strip_accents, teams_match
from sports_common.belgian_prices import choose_prices, price_label
from sports_common.kambi import OPERATORS, best_prices, kambi_get, outcome_price

logger = logging.getLogger(__name__)

KAMBI_PATHS = {
    "EPL": "england/premier_league", "LaLiga": "spain/la_liga", "SerieA": "italy/serie_a",
    "Bundesliga": "germany/bundesliga", "Ligue1": "france/ligue_1", "Belgium": "belgium/jupiler_pro_league",
    "Eredivisie": "netherlands/eredivisie", "PrimeiraLiga": "portugal/primeira_liga",
    "ScottishPrem": "scotland/scottish_premiership", "UCL": "champions_league", "UEL": "europa_league",
    "UECL": "conference_league", "NationsLeague": "uefa_nations_league", "Friendlies": "international_friendly_matches",
}  # qualifiers and finals get their own Kambi groups only while listed: add them then
ODDS_KEYS = ("odds_home", "odds_draw", "odds_away", "odds_over25", "odds_under25", "odds_btts_yes", "odds_btts_no",
             "odds_corners_over95", "odds_corners_under95")


def parse_bet_offers(bet_offers: Iterable[Dict]) -> Dict[str, float]:
    """Our odds fields from Kambi bet offers (only full-match markets, only open prices)."""
    odds: Dict[str, float] = {}
    for offer in bet_offers:
        label = (offer.get("criterion") or {}).get("label")
        kind = (offer.get("betOfferType") or {}).get("name")
        by_type = {o.get("type"): o for o in offer.get("outcomes") or []}
        if label == "Full Time" and kind == "Match":
            pairs = (("odds_home", "OT_ONE"), ("odds_draw", "OT_CROSS"), ("odds_away", "OT_TWO"))
        elif label == "Total Goals" and kind == "Over/Under" and by_type.get("OT_OVER", {}).get("line") == 2500:
            pairs = (("odds_over25", "OT_OVER"), ("odds_under25", "OT_UNDER"))
        elif label == "Total Corners" and kind == "Over/Under" and by_type.get("OT_OVER", {}).get("line") == 9500:
            pairs = (("odds_corners_over95", "OT_OVER"), ("odds_corners_under95", "OT_UNDER"))
        elif label == "Both Teams To Score" and kind == "Yes/No":
            pairs = (("odds_btts_yes", "OT_YES"), ("odds_btts_no", "OT_NO"))
        else:
            continue
        prices = {field: outcome_price(by_type.get(t, {})) for field, t in pairs}
        if None not in prices.values():  # a market counts only with every side priced
            odds.update(prices)
    return odds


def parse_list_view(payload: Dict) -> List[Dict]:
    """Matches in a league list view: Kambi id, kick-off (UTC), teams, 1X2 and O/U 2.5."""
    matches = []
    for item in payload.get("events") or []:
        event = item.get("event") or {}
        if (event.get("state") not in (None, "NOT_STARTED") or not event.get("homeName")
                or not event.get("awayName") or not event.get("start") or not event.get("id")):
            continue
        matches.append({"event_id": event["id"], "start": event["start"], "home_team": event["homeName"],
                        "away_team": event["awayName"], "odds": parse_bet_offers(item.get("betOffers") or [])})
    return matches


def fetch_league_prices(league_key: str, details_hours: float = 36, within_hours: Optional[float] = None,
                        now: Optional[datetime] = None, pause: float = 0.3) -> List[Dict]:
    """Each upcoming listed match of a league (only those kicking off within ``within_hours``, when
    given) with every Belgian book's prices: {event_id, start, home_team, away_team, books}. BTTS and
    corners (one call per match and book) are fetched for matches within ``details_hours``."""
    path = KAMBI_PATHS.get(league_key)
    if not path:
        return []
    now = now or datetime.now(timezone.utc)
    events: Dict[int, Dict] = {}
    for book, operator in OPERATORS.items():
        try:
            listed = parse_list_view(kambi_get(operator, f"listView/football/{path}.json"))
        except (requests.RequestException, ValueError, KeyError) as e:
            logger.warning(f"[Kambi] {book} {league_key}: {e}")
            continue
        for m in listed:
            start = datetime.fromisoformat(m["start"].replace("Z", "+00:00"))
            if start <= now or (within_hours is not None and start > now + timedelta(hours=within_hours)):
                continue
            odds = dict(m.pop("odds"))
            if start <= now + timedelta(hours=details_hours):
                time.sleep(pause)
                try:
                    odds.update(parse_bet_offers(kambi_get(operator, f"betoffer/event/{m['event_id']}.json").get("betOffers") or []))
                except (requests.RequestException, ValueError) as e:
                    logger.debug(f"[Kambi] {book} event {m['event_id']}: {e}")
            if odds:
                events.setdefault(m["event_id"], {**m, "league": league_key, "books": {}})["books"][book] = odds
    return list(events.values())


_EXPAND = {"st": "saint", "sint": "saint", "sp": "sporting", "internazionale": "inter", "praha": "prague",
           "kobenhavn": "copenhagen", "munchen": "munich", "zvezda": "star", "crvena": "red", "beograd": "belgrade"}
_NOISE = {"fc", "cf", "sc", "afc", "ac", "as", "sv", "sk", "kv", "krc", "kaa", "rsc", "club", "de", "the", "royal",
          "royale", "cd", "ud", "fk", "bk", "if", "ssc", "us", "city", "united", "utd"}


def _tokens(name: str) -> set:
    words = re.sub(r"[^a-z0-9 ]", " ", strip_accents(str(name)).replace("'", "")).split()
    return {_EXPAND.get(w, w) for w in words if w not in _NOISE}


def _name_score(kambi_name: str, our_name: str) -> float:
    if teams_match(kambi_name, our_name):
        return 2.0
    a, b = _tokens(kambi_name), _tokens(our_name)
    return len(a & b) / len(a | b) if a and b else 0.0


def _same_day(kickoff_utc: str, fixture_date) -> bool:
    try:
        day = datetime.fromisoformat(str(kickoff_utc).replace("Z", "+00:00")).date()
        other = datetime.fromisoformat(str(fixture_date)[:10]).date()
    except ValueError:
        return False
    return abs((day - other).days) <= 1


def match_event(event: Dict, fixtures: List[Dict]) -> Optional[int]:
    """Index of the fixture a Kambi match is: same league, kick-off within a day, and the best name
    agreement with both teams sharing a word (only a few matches a day, so this is unambiguous)."""
    best, best_score = None, 0.0
    for i, f in enumerate(fixtures):
        if (f.get("league_key") or f.get("league")) != event["league"] or not _same_day(event["start"], f.get("date")):
            continue
        home, away = _name_score(event["home_team"], f.get("home_team")), _name_score(event["away_team"], f.get("away_team"))
        if home > 0 and away > 0 and home + away > best_score:
            best, best_score = i, home + away
    return best


def merge_belgian_prices(fixtures: List[Dict], events: List[Dict]) -> int:
    """Add each event's book prices to the fixture it is (in place) and reprice the fixture from
    all its Belgian books, Napoleon first (``sports_common.belgian_prices``); returns how many."""
    priced = 0
    for event in events:
        if not {"odds_home", "odds_draw", "odds_away"} <= set(best_prices(event["books"])):
            continue
        i = match_event(event, fixtures)
        if i is None:
            continue
        f = fixtures[i]
        reference = dict(f.get("reference_odds") or {})
        previous = {k: f[k] for k in ODDS_KEYS if f.get(k)}
        if previous and not f.get("belgian_books") and "eu" not in reference:
            reference["eu"] = {**previous, "bookmaker": f.get("bookmaker")}
        books = {**(f.get("belgian_books") or {}), **event["books"]}
        prices, sources, better = choose_prices(books)
        f.update(prices)
        f.update({"reference_odds": reference, "belgian_books": books, "price_books": sources,
                  "better_elsewhere": better, "bookmaker": price_label(sources, "odds_home"),
                  "commence_time": f.get("commence_time") or event["start"]})
        if "napoleon" not in event["books"]:
            f["kambi_event_id"] = event["event_id"]  # the closing-price archive is keyed by Kambi ids
        priced += 1
    return priced


def add_belgian_prices(fixtures: List[Dict], details_hours: float = 36) -> List[Dict]:
    """Fixtures (all competitions) priced at Napoleon, else the best of Unibet and Bingoal."""
    leagues = sorted({f.get("league_key") or f.get("league") for f in fixtures} & set(KAMBI_PATHS))
    kambi = napoleon = 0
    for league_key in leagues:
        try:
            kambi += merge_belgian_prices(fixtures, fetch_league_prices(league_key, details_hours))
        except Exception as e:  # prices are optional: never lose the fixtures
            logger.warning(f"[Kambi] {league_key}: {e}")
    try:
        from football_core.data.napoleon import fetch_napoleon_prices
        napoleon = merge_belgian_prices(fixtures, fetch_napoleon_prices(leagues, details_hours))
    except Exception as e:
        logger.warning(f"[Napoleon] {e}")
    logger.info(f"[Belgian prices] Unibet/Bingoal on {kambi}, Napoleon on {napoleon} of {len(fixtures)} fixtures")
    return fixtures
