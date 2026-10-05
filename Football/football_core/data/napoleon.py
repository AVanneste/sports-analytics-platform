"""Napoleon's football prices (Superbet's offer API, see sports_common/superbet.py).

Events come back in the same shape as Kambi's (``kambi.fetch_league_prices``), with one book,
"napoleon", so ``kambi.merge_belgian_prices`` pairs them with our fixtures the same way.
"""
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

import requests

from sports_common.superbet import FOOTBALL, event_details, events_by_date, parse_prices, split_match_name

logger = logging.getLogger(__name__)

NAPOLEON_TOURNAMENTS = {  # Superbet tournamentId per competition (checked against live events, Oct 2026)
    "EPL": 106, "LaLiga": 98, "SerieA": 104, "Bundesliga": 245, "Ligue1": 100, "Belgium": 324,
    "Eredivisie": 256, "PrimeiraLiga": 142, "ScottishPrem": 4, "UCL": 80794, "UEL": 688, "UECL": 80813,
}
FIELDS = {  # field -> (marketId, outcomeId, line)
    "odds_home": (547, 1470, None), "odds_draw": (547, 1471, None), "odds_away": (547, 1472, None),
    "odds_over25": (200734, 151889, "2.5"), "odds_under25": (200734, 151888, "2.5"),
    "odds_btts_yes": (539, 1440, None), "odds_btts_no": (539, 1441, None),
    "odds_corners_over95": (704, 2043, "9.5"), "odds_corners_under95": (704, 2042, "9.5"),
}
GROUPS = (("odds_home", "odds_draw", "odds_away"), ("odds_over25", "odds_under25"),
          ("odds_btts_yes", "odds_btts_no"), ("odds_corners_over95", "odds_corners_under95"))


def parse_odds(odds: Iterable[Dict]) -> Dict[str, float]:
    return parse_prices(odds, FIELDS, GROUPS)


def to_event(event: Dict, league_key: str, odds: Dict[str, float]) -> Optional[Dict]:
    home, away = split_match_name(event.get("matchName"))
    if not home or not away or not odds:
        return None
    return {"event_id": event["eventId"], "league": league_key, "start": event.get("utcDate"),
            "home_team": home, "away_team": away, "books": {"napoleon": odds}}


def fetch_napoleon_prices(leagues: Optional[Iterable[str]] = None, details_hours: float = 36,
                          within_hours: float = 24 * 10, now: Optional[datetime] = None, pause: float = 0.3) -> List[Dict]:
    """Napoleon's prices for our competitions' matches kicking off within ``within_hours``; all
    markets (one call per match) for those within ``details_hours``, 1X2 only for the rest."""
    now = now or datetime.now(timezone.utc)
    by_tournament = {NAPOLEON_TOURNAMENTS[k]: k for k in (leagues or NAPOLEON_TOURNAMENTS) if k in NAPOLEON_TOURNAMENTS}
    out = []
    for e in events_by_date(now.replace(tzinfo=None), (now + timedelta(hours=within_hours)).replace(tzinfo=None), FOOTBALL):
        league_key = by_tournament.get(e.get("tournamentId"))
        if not league_key:
            continue
        odds = parse_odds(e.get("odds") or [])
        start = datetime.fromisoformat(str(e.get("utcDate")).replace("Z", "+00:00"))
        if start <= now + timedelta(hours=details_hours):
            time.sleep(pause)
            try:
                odds.update(parse_odds(event_details(e["eventId"]).get("odds") or []))
            except (requests.RequestException, ValueError) as err:
                logger.debug(f"[Napoleon] event {e['eventId']}: {err}")
        event = to_event(e, league_key, odds)
        if event:
            out.append(event)
    return out
