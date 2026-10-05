"""The Odds API client for fetching upcoming football matches and live market odds for Top European leagues and European Cups."""
import datetime
import json
import logging
import statistics
import time
from pathlib import Path
from typing import Dict, List, Optional
import requests

from football_core.config import LEAGUES, CACHE_DIR, ODDS_API_CACHE_FILE
from football_core.utils.helpers import normalize_team_name, teams_match
from sports_common.odds_api import ODDS_REGIONS, odds_window_params
from sports_common.secrets import get_secret, is_usable_key, redact

logger = logging.getLogger(__name__)

BASE_URL = "https://api.the-odds-api.com/v4"
QUOTA_FILE = CACHE_DIR / "quota_status.json"
ODDS_MARKETS = "h2h,totals"  # the /odds endpoint rejects btts and other non-featured markets (HTTP 422)


def is_valid_odds_api_key(api_key: Optional[str]) -> bool:
    """Validate that an Odds API key is not missing, empty, or a dummy/invalid placeholder."""
    return is_usable_key(api_key)


def get_odds_api_key(api_key: Optional[str] = None) -> str:
    """Resolve the Odds API key: explicit argument, then ODDS_API_KEY (env, .env, secrets.toml).

    Returns "" when nothing is configured; callers then use the free ESPN feed.
    """
    if api_key and api_key.strip():
        return api_key.strip()
    return get_secret("ODDS_API_KEY") or ""


def save_quota_headers(resp: requests.Response):
    """Record remaining/used quota from response headers to persistent cache."""
    try:
        QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
        remaining = resp.headers.get("x-requests-remaining")
        used = resp.headers.get("x-requests-used")

        # Only key or quota problems stop further calls; a rejected request (e.g. 422) does not
        if resp.status_code in (401, 403, 429):
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
                "ok": True,
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
    
    try:
        resp = requests.get(f"{BASE_URL}/sports/", params={"apiKey": key}, timeout=10)
        save_quota_headers(resp)
        return get_stored_quota()
    except Exception:
        return quota


def _espn_fixtures(league_key: str) -> List[Dict]:
    try:
        from football_core.data.espn_client import fetch_espn_upcoming_fixtures
        return fetch_espn_upcoming_fixtures(league_key)
    except Exception as e:
        logger.warning(f"ESPN fetch failed for {league_key}: {e}")
        return []


def _quota_exhausted() -> bool:
    quota = get_stored_quota()
    try:
        remaining = int(str(quota.get("remaining", "100")).strip())
    except (ValueError, TypeError):
        remaining = 100
    return not quota.get("ok", True) or remaining <= 0


def _days_apart(date_a: Optional[str], date_b: Optional[str]) -> int:
    try:
        return abs((datetime.date.fromisoformat(str(date_a)[:10]) - datetime.date.fromisoformat(str(date_b)[:10])).days)
    except ValueError:
        return 99


def merge_odds(fixtures: List[Dict], priced: List[Dict]) -> List[Dict]:
    """ESPN fixtures with The Odds API prices wherever the same match is priced (same teams, dates at
    most a day apart); priced matches ESPN does not list are kept as they are."""
    merged = [dict(f) for f in fixtures]
    for p in priced:
        for f in merged:
            if (teams_match(f.get("home_team"), p["home_team"]) and teams_match(f.get("away_team"), p["away_team"])
                    and _days_apart(f.get("date"), p["date"]) <= 1):
                f.update({k: v for k, v in p.items()
                          if v is not None and (k.startswith("odds_") or k in ("bookmaker", "bookmakers_count"))})
                if p.get("reference_odds"):
                    f["reference_odds"] = {**(f.get("reference_odds") or {}), **p["reference_odds"]}
                break
        else:
            merged.append(p)
    return merged


def _odds_api_matches(league_key: str, league_info: Dict, sport_key: str, api_key: str) -> List[Dict]:
    """Matches starting within the odds window, priced by the median over European bookmakers."""
    params = {"apiKey": api_key, "regions": ODDS_REGIONS, "markets": ODDS_MARKETS, "oddsFormat": "decimal",
              **odds_window_params()}
    try:
        resp = requests.get(f"{BASE_URL}/sports/{sport_key}/odds/", params=params, timeout=15)
        save_quota_headers(resp)
        if resp.status_code != 200:
            logger.warning(f"The Odds API refused {league_key} (HTTP {resp.status_code}); keeping ESPN odds")
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

            pinnacle: Dict[str, float] = {}  # the sharp price, kept as a fair-price reference
            home_odds_list = []
            draw_odds_list = []
            away_odds_list = []
            over25_odds_list = []
            under25_odds_list = []

            for bm in item.get("bookmakers", []):
                is_pinnacle = bm.get("key") == "pinnacle"
                for m in bm.get("markets", []):
                    market_key = m.get("key")
                    if market_key == "h2h":
                        for outcome in m.get("outcomes", []):
                            out_name = outcome.get("name", "")
                            norm_out_name = normalize_team_name(out_name)
                            price = float(outcome.get("price", 1.0))
                            if norm_out_name == home_team or out_name == raw_home:
                                home_odds_list.append(price)
                                field = "odds_home"
                            elif norm_out_name == away_team or out_name == raw_away:
                                away_odds_list.append(price)
                                field = "odds_away"
                            elif out_name.lower() in ["draw", "tie", "x"]:
                                draw_odds_list.append(price)
                                field = "odds_draw"
                            else:
                                continue
                            if is_pinnacle:
                                pinnacle[field] = price
                    elif market_key == "totals":
                        for outcome in m.get("outcomes", []):
                            point = outcome.get("point")
                            if point == 2.5:
                                out_name = outcome.get("name", "").lower()
                                price = float(outcome.get("price", 1.0))
                                if "over" in out_name:
                                    over25_odds_list.append(price)
                                    if is_pinnacle:
                                        pinnacle["odds_over25"] = price
                                elif "under" in out_name:
                                    under25_odds_list.append(price)
                                    if is_pinnacle:
                                        pinnacle["odds_under25"] = price

            h_med = round(float(statistics.median(home_odds_list)), 2) if home_odds_list else None
            d_med = round(float(statistics.median(draw_odds_list)), 2) if draw_odds_list else None
            a_med = round(float(statistics.median(away_odds_list)), 2) if away_odds_list else None

            h_best = max(home_odds_list) if home_odds_list else None
            d_best = max(draw_odds_list) if draw_odds_list else None
            a_best = max(away_odds_list) if away_odds_list else None

            over_med = round(float(statistics.median(over25_odds_list)), 2) if over25_odds_list else None
            under_med = round(float(statistics.median(under25_odds_list)), 2) if under25_odds_list else None

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
                "bookmaker": "The Odds API (European median)",
                "bookmakers_count": len(item.get("bookmakers", [])),
                "reference_odds": {"pinnacle": pinnacle} if pinnacle else {},
            })

        return matches
    except Exception as e:
        logger.warning(f"Error fetching odds for {league_key}: {redact(e)}")
        return []


def fetch_league_odds(league_key: str, api_key: Optional[str] = None) -> List[Dict]:
    """Upcoming fixtures for a league or cup: ESPN's schedule (with DraftKings odds), repriced with the
    median European odds from The Odds API for the matches that start within the odds window."""
    league_info = LEAGUES.get(league_key)
    if not league_info:
        logger.warning(f"Unknown league {league_key}")
        return []
    fixtures = _espn_fixtures(league_key)
    sport_key = league_info.get("odds_key")
    resolved_key = get_odds_api_key(api_key)
    if not sport_key or not is_valid_odds_api_key(resolved_key) or _quota_exhausted():
        return fixtures
    return merge_odds(fixtures, _odds_api_matches(league_key, league_info, sport_key, resolved_key))


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

    if is_valid_odds_api_key(resolved_key):
        fetch_odds_api_quota(resolved_key)  # free call: a new month or a new key clears an old failure
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

    # The prices bets can be placed at: Unibet.be and Bingoal, through Kambi's public feed
    try:
        from football_core.data.kambi import add_belgian_prices
        add_belgian_prices(all_fixtures)
    except Exception as e:
        logger.warning(f"Belgian prices unavailable: {redact(e)}")

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
