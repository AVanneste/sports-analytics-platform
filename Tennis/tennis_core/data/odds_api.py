"""The Odds API client for fetching real-time tennis matches and live market betting odds."""
import json
import logging
import statistics
from pathlib import Path
from typing import Dict, List, Optional
import requests

from tennis_core.config import UPCOMING_DATA_DIR
from tennis_core.utils.helpers import normalize_player_name, normalize_surface

logger = logging.getLogger(__name__)

DEFAULT_ODDS_API_KEY = "2248b63df4643a6eb03b7918e9cb3226"
BASE_URL = "https://api.the-odds-api.com/v4"
QUOTA_FILE = UPCOMING_DATA_DIR / "quota_status.json"


def save_quota_headers(resp: requests.Response):
    """Record remaining/used quota from response headers to persistent cache."""
    try:
        remaining = resp.headers.get("x-requests-remaining")
        used = resp.headers.get("x-requests-used")
        if remaining is not None or used is not None:
            QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "remaining": remaining or "?",
                "used": used or "?",
                "ok": resp.status_code == 200,
                "status_code": resp.status_code,
            }
            with open(QUOTA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
    except Exception as e:
        logger.debug(f"Could not persist quota headers: {e}")


def get_stored_quota() -> Dict:
    """Retrieve the most recently recorded API quota status."""
    if QUOTA_FILE.exists():
        try:
            with open(QUOTA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"remaining": "?", "used": "?", "ok": False}


def fetch_all_active_tennis_sports(api_key: str = DEFAULT_ODDS_API_KEY) -> List[Dict]:
    """Fetch list of all currently active tennis sports/tournaments on The Odds API."""
    url = f"{BASE_URL}/sports/?apiKey={api_key}"
    try:
        resp = requests.get(url, timeout=15)
        save_quota_headers(resp)
        if resp.status_code == 200:
            sports = resp.json()
            return [s for s in sports if "tennis" in s.get("key", "").lower() or "tennis" in s.get("group", "").lower()]
        else:
            logger.warning(f"Failed to fetch sports list from The Odds API (HTTP {resp.status_code})")
            return []
    except Exception as e:
        logger.warning(f"Error fetching sports list: {e}")
        return []


def fetch_tennis_odds_for_sport(sport_key: str, api_key: str = DEFAULT_ODDS_API_KEY) -> List[Dict]:
    """Fetch real-time upcoming matches and odds for a specific tennis tournament."""
    url = f"{BASE_URL}/sports/{sport_key}/odds/?apiKey={api_key}&regions=eu,us,uk&markets=h2h"
    try:
        resp = requests.get(url, timeout=15)
        save_quota_headers(resp)
        if resp.status_code != 200:
            logger.warning(f"Failed to fetch odds for {sport_key} (HTTP {resp.status_code})")
            return []
        
        data = resp.json()
        matches = []

        circuit = "WTA" if "wta" in sport_key.lower() else "ATP"
        
        # Surface deduction from tournament key/name
        surface = "Hard"
        if any(c in sport_key.lower() for c in ["clay", "french_open", "madrid", "rome", "monte_carlo", "barcelona", "hamburg", "stuttgart"]):
            surface = "Clay"
        elif any(g in sport_key.lower() for g in ["grass", "wimbledon", "halle", "queens", "bad_homburg"]):
            surface = "Grass"

        for item in data:
            home = item.get("home_team", "")
            away = item.get("away_team", "")
            commence_time = item.get("commence_time", "")
            date_str = commence_time[:10] if commence_time else "Upcoming"

            p1 = normalize_player_name(home)
            p2 = normalize_player_name(away)

            # Aggregate best / consensus odds across all bookmakers
            p1_odds_list = []
            p2_odds_list = []

            for bm in item.get("bookmakers", []):
                for m in bm.get("markets", []):
                    if m.get("key") == "h2h":
                        for outcome in m.get("outcomes", []):
                            name = normalize_player_name(outcome.get("name", ""))
                            price = float(outcome.get("price", 1.0))
                            if name == p1 or outcome.get("name") == home:
                                p1_odds_list.append(price)
                            elif name == p2 or outcome.get("name") == away:
                                p2_odds_list.append(price)

            p1_median_odds = round(float(statistics.median(p1_odds_list)), 2) if p1_odds_list else None
            p2_median_odds = round(float(statistics.median(p2_odds_list)), 2) if p2_odds_list else None
            p1_best_odds = max(p1_odds_list) if p1_odds_list else None
            p2_best_odds = max(p2_odds_list) if p2_odds_list else None

            tourney_title = sport_key.replace("tennis_", "").replace("_", " ").title()

            matches.append({
                "match_id": item.get("id"),
                "circuit": circuit,
                "tourney_name": tourney_title,
                "surface": surface,
                "round": "Main Draw",
                "date": date_str,
                "commence_time": commence_time,
                "p1_name": p1,
                "p2_name": p2,
                "p1_odds": p1_median_odds or p1_best_odds,
                "p2_odds": p2_median_odds or p2_best_odds,
                "p1_best_odds": p1_best_odds,
                "p2_best_odds": p2_best_odds,
                "bookmakers_count": len(item.get("bookmakers", [])),
            })

        return matches
    except Exception as e:
        logger.warning(f"Error fetching odds for {sport_key}: {e}")
        return []


def fetch_all_live_tennis_matches(api_key: str = DEFAULT_ODDS_API_KEY) -> List[Dict]:
    """Fetch all real upcoming tennis matches across all active tournaments."""
    active_sports = fetch_all_active_tennis_sports(api_key)
    all_matches = []
    
    for s in active_sports:
        sport_key = s.get("key")
        if sport_key:
            logger.info(f"Fetching real upcoming matches for {sport_key}...")
            matches = fetch_tennis_odds_for_sport(sport_key, api_key)
            all_matches.extend(matches)
            
    logger.info(f"Retrieved {len(all_matches)} real upcoming tennis matches from The Odds API.")
    return all_matches
