"""Kambi's public offering feed, shared by football and tennis: Unibet.be and Bingoal prices.

Both Belgian books run on Kambi, whose JSON feed (the one their websites read) needs no key.
Prices come in thousandths (1910 is 1.91), lines too (2500 is 2.5).
"""
import time
from typing import Dict, Optional

import requests

BASE_URL = "https://eu-offering-api.kambicdn.com/offering/v2018"
OPERATORS = {"unibet": "ubbe", "bingoal": "bingoalbe"}  # Napoleon is on Kambi too; its code is unknown
_PARAMS = {"lang": "en_GB", "market": "BE"}
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0"})


def kambi_get(operator: str, path: str, retries: int = 2) -> Dict:
    """GET a feed path for one operator, retrying dropped connections, throttling and 5xx."""
    for attempt in range(retries + 1):
        try:
            response = _SESSION.get(f"{BASE_URL}/{operator}/{path}", params=_PARAMS, timeout=20)
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


def outcome_price(outcome: Dict) -> Optional[float]:
    """Decimal price of an open outcome, else None."""
    odds = outcome.get("odds")
    if not odds or outcome.get("status", "OPEN") != "OPEN":
        return None
    return round(odds / 1000.0, 3)


def best_prices(books: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    """The highest price per selection across books."""
    best: Dict[str, float] = {}
    for odds in books.values():
        for key, value in odds.items():
            if value and value > best.get(key, 0.0):
                best[key] = value
    return best
