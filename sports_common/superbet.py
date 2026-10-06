"""Napoleon's prices: Superbet's public offer API (Napoleon runs on Superbet's platform).

napoleonsports.be reads its odds from this host (``offerServer`` in its runtime config); it needs
no key. ``events/by-date`` lists events with their main market; ``events/{id}`` has every market
(about 1 MB a match, no filtering). Market and outcome ids are stable numbers: see the parsers in
football_core/data/napoleon.py and tennis_core/data/kambi_tennis.py.
"""
import time
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

import requests

BASE_URL = "https://production-superbet-offer-ng-be.freetls.fastly.net/v2/en-BE"
FOOTBALL, TENNIS = 5, 2  # sportId
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0"})


def superbet_get(path: str, params: Optional[Dict] = None, retries: int = 2) -> Dict:
    """GET an offer API path, retrying dropped connections, throttling and 5xx."""
    for attempt in range(retries + 1):
        try:
            response = _SESSION.get(f"{BASE_URL}/{path}", params=params, timeout=30)
        except requests.ConnectionError:
            if attempt == retries:
                raise
            time.sleep(5 * (attempt + 1))
            continue
        if response.status_code not in (429, 500, 502, 503, 504) or attempt == retries:
            response.raise_for_status()
            return response.json()
        time.sleep(5 * (attempt + 1))
    return {}


def events_by_date(start: datetime, end: datetime, sport_id: Optional[int] = None, chunk_hours: int = 12) -> List[Dict]:
    """Prematch events kicking off in [start, end) (UTC), fetched in chunks."""
    events, cursor = {}, start
    while cursor < end:
        stop = min(cursor + timedelta(hours=chunk_hours), end)
        payload = superbet_get("events/by-date", {"currentStatus": "active", "offerState": "prematch",
                                                  "startDate": cursor.strftime("%Y-%m-%d %H:%M:%S"),
                                                  "endDate": stop.strftime("%Y-%m-%d %H:%M:%S")})
        for e in payload.get("data") or []:
            if sport_id is None or e.get("sportId") == sport_id:
                events[e["eventId"]] = e
        cursor = stop
    return list(events.values())


def event_details(event_id: int) -> Dict:
    data = superbet_get(f"events/{event_id}").get("data") or []
    return data[0] if data else {}


def tournament_names() -> Dict[int, str]:
    """tournamentId -> English name, for every tournament on offer (about 2.5 MB)."""
    tournaments = (superbet_get("struct").get("data") or {}).get("tournaments") or []
    return {int(t["id"]): (t.get("localNames") or {}).get("en-BE", "") for t in tournaments}


def split_match_name(name: str) -> Tuple[str, str]:
    """'SK Beveren·Lommel SK' -> ('SK Beveren', 'Lommel SK')."""
    home, _, away = str(name).partition("·")
    return home.strip(), away.strip()


def parse_prices(odds: Iterable[Dict], fields: Dict[str, Tuple[int, int, Optional[str]]],
                 groups: Iterable[Tuple[str, ...]]) -> Dict[str, float]:
    """Our fields from Superbet odds: ``fields`` maps a field to (marketId, outcomeId, line or None);
    a market counts only when every field of its group is priced and active."""
    found: Dict[str, float] = {}
    wanted = {spec: field for field, spec in fields.items()}
    for o in odds:
        key = (o.get("marketId"), o.get("outcomeId"), o.get("specialBetValue") or None)
        field = wanted.get(key)
        if field and o.get("status") == "active" and o.get("price"):
            found[field] = round(float(o["price"]), 3)
    return {f: found[f] for group in groups if all(f in found for f in group) for f in group}
