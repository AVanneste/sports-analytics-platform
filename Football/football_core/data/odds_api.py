"""The Odds API client for fetching upcoming football matches and live market odds for Top European leagues and European Cups."""
import json
import logging
import os
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


def is_valid_odds_api_key(api_key: Optional[str]) -> bool:
    """Validate that an Odds API key is not missing, empty, or a dummy/invalid placeholder."""
    if not api_key:
        return False
    k = str(api_key).strip().lower()
    return k not in ("", "none", "null", "invalid", "false", "test", "dummy")


def get_odds_api_key(api_key: Optional[str] = None) -> str:
    """Retrieve Odds API key with priority: explicit arg -> Streamlit secrets -> OS env -> fallback."""
    if api_key and api_key.strip():
        return api_key.strip()
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "ODDS_API_KEY" in st.secrets:
            return str(st.secrets["ODDS_API_KEY"]).strip()
    except Exception:
        pass
    env_k = os.environ.get("ODDS_API_KEY")
    if env_k and env_k.strip():
        return env_k.strip()
    return DEFAULT_ODDS_API_KEY


def save_quota_headers(resp: requests.Response):
    """Record remaining/used quota from response headers to persistent cache."""
    try:
        QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
        remaining = resp.headers.get("x-requests-remaining")
        used = resp.headers.get("x-requests-used")
        is_ok = (resp.status_code == 200)

        # In case of auth error, unprocessable entity, or rate limit (401, 403, 422, 429)
        if resp.status_code in (401, 403, 422, 429) or not is_ok:
            data = {
                "remaining": "0" if remaining is None else str(remaining),
                "used": "?" if used is None else str(used),
                "ok": False,
                "status_code": resp.status_code,
                "timestamp": time.time(),
            }
        else:
            data = {
                "remaining": str(remaining) if remaining is not None else "?",
                "used": str(used) if used is not None else "?",
                "ok": is_ok,
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
    key = get_odds_api_key(api_key)
    if not is_valid_odds_api_key(key):
        return {"remaining": "0", "used": "?", "ok": False, "status_code": 401}
    quota = get_stored_quota()
    if quota.get("ok") and (time.time() - quota.get("timestamp", 0) < 300):
        return quota
    if not quota.get("ok", True) and (time.time() - quota.get("timestamp", 0) < 3600):
        return quota
    
    url = f"{BASE_URL}/sports/?apiKey={key}"
    try:
        resp = requests.get(url, timeout=10)
        save_quota_headers(resp)
        return get_stored_quota()
    except Exception:
        return quota


def fetch_league_odds(league_key: str, api_key: Optional[str] = None) -> List[Dict]:
    """Fetch real-time upcoming matches and 1X2 / totals odds for a specific league or cup."""
    league_info = LEAGUES.get(league_key)
    if not league_info:
        logger.warning(f"Unknown league {league_key}")
        return []

    # 1. Immediate fallback if competition has no Odds API sport key
    sport_key = league_info.get("odds_key")
    if not sport_key:
        logger.debug(f"League {league_key} has no odds_key. Using ESPN client directly...")
        try:
            from football_core.data.espn_client import fetch_espn_upcoming_fixtures
            return fetch_espn_upcoming_fixtures(league_key)
        except Exception as e:
            logger.warning(f"ESPN fetch failed for {league_key}: {e}")
            return []

    # 2. Immediate fallback if key is invalid, placeholder, or missing
    resolved_key = get_odds_api_key(api_key)
    if not is_valid_odds_api_key(resolved_key):
        logger.info(f"Odds API key is invalid/unconfigured ('{resolved_key}'). Using ESPN for {league_key}...")
        try:
            from football_core.data.espn_client import fetch_espn_upcoming_fixtures
            return fetch_espn_upcoming_fixtures(league_key)
        except Exception as e:
            logger.warning(f"ESPN fallback failed for {league_key}: {e}")
            return []

    # 3. Check stored quota before wasting an API call if already depleted or failed
    quota = get_stored_quota()
    try:
        rem = int(str(quota.get("remaining", "100")).strip())
    except (ValueError, TypeError):
        rem = 100
    if not quota.get("ok", True) or rem <= 0:
        logger.info(f"Odds API quota exhausted (ok: {quota.get('ok')}, remaining: {rem}). Using ESPN for {league_key}...")
        try:
            from football_core.data.espn_client import fetch_espn_upcoming_fixtures
            return fetch_espn_upcoming_fixtures(league_key)
        except Exception as e:
            logger.warning(f"ESPN fallback failed for {league_key}: {e}")
            return []

    url = f"{BASE_URL}/sports/{sport_key}/odds/?apiKey={resolved_key}&regions=eu,uk,us&markets=h2h,totals,btts&oddsFormat=decimal"
    
    try:
        resp = requests.get(url, timeout=15)
        save_quota_headers(resp)
        if resp.status_code != 200:
            logger.warning(f"Failed to fetch odds for {league_key} (HTTP {resp.status_code}), falling back to ESPN...")
            try:
                from football_core.data.espn_client import fetch_espn_upcoming_fixtures
                return fetch_espn_upcoming_fixtures(league_key)
            except Exception as e:
                logger.warning(f"ESPN fallback failed for {league_key}: {e}")
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
            corners_over95_list = []
            corners_under95_list = []
            cards_over35_list = []
            cards_under35_list = []

            for bm in item.get("bookmakers", []):
                for m in bm.get("markets", []):
                    market_key = m.get("key")
                    market_desc = (m.get("description", "") or "").lower()
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
                    elif market_key == "alternate_totals":
                        # Parse corner and card totals from alternate markets
                        is_corners = "corner" in market_desc
                        is_cards = "card" in market_desc
                        for outcome in m.get("outcomes", []):
                            point = outcome.get("point")
                            out_name = (outcome.get("name", "") or "").lower()
                            price = float(outcome.get("price", 1.0))
                            if is_corners and point == 9.5:
                                if "over" in out_name:
                                    corners_over95_list.append(price)
                                elif "under" in out_name:
                                    corners_under95_list.append(price)
                            elif is_cards and point == 3.5:
                                if "over" in out_name:
                                    cards_over35_list.append(price)
                                elif "under" in out_name:
                                    cards_under35_list.append(price)

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

            corners_o95_med = round(float(statistics.median(corners_over95_list)), 2) if corners_over95_list else None
            corners_u95_med = round(float(statistics.median(corners_under95_list)), 2) if corners_under95_list else None
            cards_o35_med = round(float(statistics.median(cards_over35_list)), 2) if cards_over35_list else None
            cards_u35_med = round(float(statistics.median(cards_under35_list)), 2) if cards_under35_list else None

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
                "odds_corners_over95": corners_o95_med,
                "odds_corners_under95": corners_u95_med,
                "odds_cards_over35": cards_o35_med,
                "odds_cards_under35": cards_u35_med,
                "bookmakers_count": len(item.get("bookmakers", [])),
            })

        if not matches:
            try:
                from football_core.data.espn_client import fetch_espn_upcoming_fixtures
                espn_m = fetch_espn_upcoming_fixtures(league_key)
                if espn_m:
                    logger.info(f"The Odds API returned 0 matches for {league_key}, loaded {len(espn_m)} via ESPN.")
                    return espn_m
            except Exception as e:
                logger.debug(f"ESPN fallback for {league_key} returned error: {e}")

        return matches
    except Exception as e:
        logger.warning(f"Error fetching odds for {league_key}: {e}")
        try:
            from football_core.data.espn_client import fetch_espn_upcoming_fixtures
            return fetch_espn_upcoming_fixtures(league_key)
        except Exception:
            return []


def fetch_all_live_upcoming_fixtures(api_key: Optional[str] = None, use_cache: bool = True) -> List[Dict]:
    """Fetch upcoming fixtures across all national leagues, European Cups, and international tournaments."""
    resolved_key = get_odds_api_key(api_key)
    cache_path = CACHE_DIR / "live_upcoming_fixtures.json"
    if use_cache and cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
                if cached and time.time() - cached.get("timestamp", 0) < 7200:
                    return cached.get("matches", [])
        except Exception:
            pass

    quota = get_stored_quota()
    try:
        rem = int(str(quota.get("remaining", "100")).strip())
    except (ValueError, TypeError):
        rem = 100
    skip_odds_api = (not is_valid_odds_api_key(resolved_key)) or (not quota.get("ok", True)) or (rem <= 0)

    all_fixtures = []
    if skip_odds_api:
        logger.info(f"Odds API bypassed (key valid: {is_valid_odds_api_key(resolved_key)}, quota ok: {quota.get('ok')}, rem: {rem}). Querying ESPN across all competitions...")
        try:
            from football_core.data.espn_client import fetch_espn_upcoming_fixtures
            for league_key in LEAGUES.keys():
                try:
                    espn_fixtures = fetch_espn_upcoming_fixtures(league_key)
                    if espn_fixtures:
                        all_fixtures.extend(espn_fixtures)
                except Exception as e:
                    logger.warning(f"Direct ESPN fetching failed for {league_key}: {e}")
        except Exception as e:
            logger.warning(f"Direct ESPN initialization failed: {e}")
    else:
        for league_key in LEAGUES.keys():
            logger.info(f"Fetching upcoming matches for {league_key}... ")
            try:
                league_matches = fetch_league_odds(league_key, resolved_key)
                if league_matches:
                    all_fixtures.extend(league_matches)
            except Exception as e:
                logger.warning(f"Failed fetching matches for {league_key}: {e}")

    # If The Odds API returned 0 matches (e.g. quota exhausted or no active feed),
    # query ESPN's real fixture schedule and consensus market odds
    if not all_fixtures and not skip_odds_api:
        logger.info("The Odds API returned 0 fixtures. Falling back to real ESPN scheduled fixtures and DraftKings odds...")
        try:
            from football_core.data.espn_client import fetch_espn_upcoming_fixtures
            for league_key in LEAGUES.keys():
                try:
                    espn_fixtures = fetch_espn_upcoming_fixtures(league_key)
                    if espn_fixtures:
                        all_fixtures.extend(espn_fixtures)
                except Exception as e:
                    logger.warning(f"ESPN fallback failed for {league_key}: {e}")
            logger.info(f"Loaded {len(all_fixtures)} 100% real upcoming fixtures across competitions via ESPN.")
        except Exception as e:
            logger.warning(f"ESPN fallback setup failed: {e}")

    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if all_fixtures:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump({"timestamp": time.time(), "matches": all_fixtures}, f, indent=2)
        elif cache_path.exists():
            # If upstream returned empty, retain existing future matches
            with open(cache_path, "r", encoding="utf-8") as f:
                old = json.load(f)
            return old.get("matches", [])
    except Exception as e:
        logger.debug(f"Failed to cache fixtures: {e}")

    return all_fixtures
