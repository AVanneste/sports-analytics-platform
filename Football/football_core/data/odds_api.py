"""The Odds API client for fetching upcoming football matches and live market odds for Top European leagues and European Cups."""
import json
import logging
import statistics
import time
from pathlib import Path
from typing import Dict, List, Optional
import requests

from football_core.config import LEAGUES, CACHE_DIR, ODDS_API_CACHE_FILE
from football_core.utils.helpers import normalize_team_name

logger = logging.getLogger(__name__)

DEFAULT_ODDS_API_KEY = "2248b63df4643a6eb03b7918e9cb3226"
BASE_URL = "https://api.the-odds-api.com/v4"
QUOTA_FILE = CACHE_DIR / "quota_status.json"


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
                "timestamp": time.time(),
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


def fetch_odds_api_quota(api_key: Optional[str] = None) -> Dict:
    """Fetch current quota status from Odds API or stored cache."""
    api_key = get_odds_api_key(api_key)
    quota = get_stored_quota()
    if quota.get("ok") and (time.time() - quota.get("timestamp", 0) < 300):
        return quota
    
    url = f"{BASE_URL}/sports/?apiKey={api_key}"
    try:
        resp = requests.get(url, timeout=10)
        save_quota_headers(resp)
        return get_stored_quota()
    except Exception:
        return quota


def fetch_league_odds(league_key: str, api_key: Optional[str] = None) -> List[Dict]:
    """Fetch real-time upcoming matches and 1X2 / totals odds for a specific league or cup."""
    api_key = get_odds_api_key(api_key)
    league_info = LEAGUES.get(league_key)
    if not league_info:
        logger.warning(f"Unknown league {league_key}")
        return []

    sport_key = league_info["odds_key"]
    url = f"{BASE_URL}/sports/{sport_key}/odds/?apiKey={api_key}&regions=eu,uk,us&markets=h2h,totals&oddsFormat=decimal"
    
    try:
        resp = requests.get(url, timeout=15)
        save_quota_headers(resp)
        if resp.status_code != 200:
            logger.warning(f"Failed to fetch odds for {league_key} (HTTP {resp.status_code})")
            return []

        data = resp.json()
        matches = []

        for item in data:
            raw_home = item.get("home_team", "")
            raw_away = item.get("away_team", "")
            commence_time = item.get("commence_time", "")
            date_str = commence_time[:10] if commence_time else "Upcoming"

            home_team = normalize_team_name(raw_home)
            away_team = normalize_team_name(raw_away)

            home_odds_list = []
            draw_odds_list = []
            away_odds_list = []
            over25_odds_list = []
            under25_odds_list = []
            btts_yes_list = []
            btts_no_list = []

            for bm in item.get("bookmakers", []):
                for m in bm.get("markets", []):
                    market_key = m.get("key")
                    if market_key == "h2h":
                        for outcome in m.get("outcomes", []):
                            out_name = outcome.get("name", "")
                            norm_out_name = normalize_team_name(out_name)
                            price = float(outcome.get("price", 1.0))
                            if norm_out_name == home_team or out_name == raw_home:
                                home_odds_list.append(price)
                            elif norm_out_name == away_team or out_name == raw_away:
                                away_odds_list.append(price)
                            elif out_name.lower() in ["draw", "tie", "x"]:
                                draw_odds_list.append(price)
                    elif market_key == "totals":
                        for outcome in m.get("outcomes", []):
                            point = outcome.get("point")
                            if point == 2.5:
                                out_name = outcome.get("name", "").lower()
                                price = float(outcome.get("price", 1.0))
                                if "over" in out_name:
                                    over25_odds_list.append(price)
                                elif "under" in out_name:
                                    under25_odds_list.append(price)
                    elif market_key in ["btts", "both_teams_to_score"]:
                        for outcome in m.get("outcomes", []):
                            out_name = outcome.get("name", "").lower()
                            price = float(outcome.get("price", 1.0))
                            if "yes" in out_name:
                                btts_yes_list.append(price)
                            elif "no" in out_name:
                                btts_no_list.append(price)

            h_med = round(float(statistics.median(home_odds_list)), 2) if home_odds_list else None
            d_med = round(float(statistics.median(draw_odds_list)), 2) if draw_odds_list else None
            a_med = round(float(statistics.median(away_odds_list)), 2) if away_odds_list else None
            
            h_best = max(home_odds_list) if home_odds_list else None
            d_best = max(draw_odds_list) if draw_odds_list else None
            a_best = max(away_odds_list) if away_odds_list else None

            over_med = round(float(statistics.median(over25_odds_list)), 2) if over25_odds_list else None
            under_med = round(float(statistics.median(under25_odds_list)), 2) if under25_odds_list else None

            btts_y_med = round(float(statistics.median(btts_yes_list)), 2) if btts_yes_list else None
            btts_n_med = round(float(statistics.median(btts_no_list)), 2) if btts_no_list else None

            matches.append({
                "match_id": item.get("id"),
                "league": league_key,
                "league_name": league_info["name"],
                "flag": league_info["flag"],
                "date": date_str,
                "commence_time": commence_time,
                "home_team": home_team,
                "away_team": away_team,
                "odds_home": h_med or h_best,
                "odds_draw": d_med or d_best,
                "odds_away": a_med or a_best,
                "odds_home_best": h_best,
                "odds_draw_best": d_best,
                "odds_away_best": a_best,
                "odds_over25": over_med,
                "odds_under25": under_med,
                "odds_btts_yes": btts_y_med,
                "odds_btts_no": btts_n_med,
                "odds_corners_over95": None,
                "odds_corners_under95": None,
                "odds_cards_over35": None,
                "odds_cards_under35": None,
                "bookmakers_count": len(item.get("bookmakers", [])),
            })

        return matches
    except Exception as e:
        logger.warning(f"Error fetching odds for {league_key}: {e}")
        return []


def fetch_all_live_upcoming_fixtures(api_key: Optional[str] = None, use_cache: bool = True) -> List[Dict]:
    """Fetch upcoming fixtures across all national leagues and European Cups."""
    api_key = get_odds_api_key(api_key)
    cache_path = CACHE_DIR / "live_upcoming_fixtures.json"
    if use_cache and cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
                if cached and time.time() - cached.get("timestamp", 0) < 7200:
                    return cached.get("matches", [])
        except Exception:
            pass

    all_fixtures = []
    for league_key in LEAGUES.keys():
        logger.info(f"Fetching upcoming matches for {league_key}... ")
        league_matches = fetch_league_odds(league_key, api_key)
        all_fixtures.extend(league_matches)

    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"timestamp": time.time(), "matches": all_fixtures}, f, indent=2)
    except Exception as e:
        logger.debug(f"Failed to cache fixtures: {e}")

    return all_fixtures
