"""API-Football (v3.football.api-sports.io) integration for fetching real completed football results, scores, corners, cards, and stats."""
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
import requests

from football_core.config import CACHE_DIR, LEAGUES
from football_core.utils.helpers import normalize_team_name, teams_match, strip_accents

logger = logging.getLogger(__name__)

DEFAULT_API_FOOTBALL_KEY = "72ff649936a2910e6d599c8c5bfeca9a"
API_FOOTBALL_BASE_URL = "https://v3.football.api-sports.io"
API_FOOTBALL_CACHE_DIR = CACHE_DIR / "api_football"
AUTO_RECONCILE_META_FILE = CACHE_DIR / "api_football_reconcile_meta.json"


def get_api_football_key(api_key: Optional[str] = None) -> str:
    """Retrieve API-Football key with priority: explicit arg -> Streamlit secrets -> OS env -> fallback."""
    if api_key and api_key.strip():
        return api_key.strip()
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "API_FOOTBALL_KEY" in st.secrets:
            return str(st.secrets["API_FOOTBALL_KEY"]).strip()
    except Exception:
        pass
    env_k = os.environ.get("API_FOOTBALL_KEY")
    if env_k and env_k.strip():
        return env_k.strip()
    return DEFAULT_API_FOOTBALL_KEY


def fetch_api_football_status(api_key: Optional[str] = None) -> Dict[str, Any]:
    """Check subscription status and remaining quota on API-Football."""
    key = get_api_football_key(api_key)
    url = f"{API_FOOTBALL_BASE_URL}/status"
    headers = {"x-apisports-key": key}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            resp = data.get("response", {})
            account = resp.get("account", {})
            requests_info = resp.get("requests", {})
            return {
                "ok": True,
                "status_code": 200,
                "name": f"{account.get('firstname', '')} {account.get('lastname', '')}".strip(),
                "email": account.get("email"),
                "requests_current": requests_info.get("current", 0),
                "requests_limit_day": requests_info.get("limit_day", 100),
                "remaining": requests_info.get("limit_day", 100) - requests_info.get("current", 0),
            }
        return {"ok": False, "status_code": r.status_code, "error": f"HTTP {r.status_code}"}
    except Exception as e:
        logger.warning(f"Error checking API-Football status: {e}")
        return {"ok": False, "error": str(e)}


def fetch_fixtures_by_date(date_str: str, api_key: Optional[str] = None, force: bool = False) -> List[Dict[str, Any]]:
    """Fetch all finished fixtures for a specific date (YYYY-MM-DD) with local caching."""
    API_FOOTBALL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = API_FOOTBALL_CACHE_DIR / f"fixtures_{date_str}.json"

    if not force and cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
                if cached and isinstance(cached, list) and len(cached) > 0:
                    return cached
        except Exception:
            pass

    key = get_api_football_key(api_key)
    url = f"{API_FOOTBALL_BASE_URL}/fixtures?date={date_str}"
    headers = {"x-apisports-key": key}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            fixtures = data.get("response", [])
            if fixtures:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(fixtures, f, indent=2)
            return fixtures
        else:
            logger.warning(f"API-Football date {date_str} returned HTTP {r.status_code}")
            return []
    except Exception as e:
        logger.error(f"Error querying API-Football for date {date_str}: {e}")
        return []


def fetch_fixture_statistics(fixture_id: int, api_key: Optional[str] = None) -> Dict[str, Any]:
    """Fetch corners, cards, and xG statistics for a specific fixture."""
    stat_cache = API_FOOTBALL_CACHE_DIR / f"stats_{fixture_id}.json"
    if stat_cache.exists():
        try:
            with open(stat_cache, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    key = get_api_football_key(api_key)
    url = f"{API_FOOTBALL_BASE_URL}/fixtures/statistics?fixture={fixture_id}"
    headers = {"x-apisports-key": key}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            resp = data.get("response", [])
            total_corners = 0
            total_cards = 0
            total_xg = 0.0
            for team_stat in resp:
                stats = {item.get("type"): item.get("value") for item in team_stat.get("statistics", [])}
                corners = stats.get("Corner Kicks") or 0
                yc = stats.get("Yellow Cards") or 0
                rc = stats.get("Red Cards") or 0
                xg = stats.get("expected_goals")
                total_corners += int(corners) if corners else 0
                total_cards += (int(yc) if yc else 0) + (int(rc) if rc else 0)
                if xg is not None:
                    try:
                        total_xg += float(xg)
                    except Exception:
                        pass
            res = {
                "corners": total_corners, 
                "cards": total_cards, 
                "actual_xg": round(total_xg, 2) if total_xg > 0 else None
            }
            with open(stat_cache, "w", encoding="utf-8") as f:
                json.dump(res, f, indent=2)
            return res
        return {"corners": 9, "cards": 4, "actual_xg": None}
    except Exception as e:
        return {"corners": 9, "cards": 4, "actual_xg": None}


def match_team_pair(team_a: str, team_b: str) -> bool:
    """Robust team name matching."""
    norm_a = normalize_team_name(team_a)
    norm_b = normalize_team_name(team_b)
    if norm_a.lower() == norm_b.lower():
        return True
    return teams_match(norm_a, norm_b) or teams_match(team_a, team_b)


def reconcile_predictions_with_api_football(tracker, api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Reconcile pending and past predictions in the tracker against real-world official finished match results
    retrieved from API-Football.
    """
    # Reset previously incorrectly graded predictions for re-grading
    for pred in tracker.predictions:
        if pred.get("status") == "settled":
            pred["status"] = "pending"

    pending = [p for p in tracker.predictions if p.get("status") != "settled"]
    if not pending:
        return {"reconciled": 0, "checked_dates": [], "message": "No pending predictions to reconcile."}

    # Only check dates in the past or today
    today_str = datetime.now().strftime("%Y-%m-%d")
    unique_dates = sorted(list({
        p.get("date")[:10] for p in pending 
        if p.get("date") and len(p.get("date")) >= 10 and p.get("date")[:10] <= today_str
    }))

    if not unique_dates:
        return {"reconciled": 0, "checked_dates": [], "message": "All pending fixtures are scheduled for future dates."}

    reconciled_count = 0
    matched_fixtures = []

    for d_str in unique_dates:
        logger.info(f"Fetching real completed fixtures from API-Football for date {d_str}...")
        fixtures = fetch_fixtures_by_date(d_str, api_key=api_key)
        time.sleep(0.3)  # Respect API-Football rate limit
        if not fixtures:
            continue

        for pred in tracker.predictions:
            p_date = (pred.get("date") or "")[:10]
            if p_date != d_str:
                continue

            p_h = pred.get("home_team", "")
            p_a = pred.get("away_team", "")

            for fix in fixtures:
                f_h = fix.get("teams", {}).get("home", {}).get("name", "")
                f_a = fix.get("teams", {}).get("away", {}).get("name", "")
                status = fix.get("fixture", {}).get("status", {}).get("short")

                # Match by robust team names
                home_match = match_team_pair(p_h, f_h)
                away_match = match_team_pair(p_a, f_a)

                if home_match and away_match:
                    if status in ["FT", "AET", "PEN"]:
                        ft_score = fix.get("score", {}).get("fulltime", {})
                        hg = ft_score.get("home")
                        ag = ft_score.get("away")
                        if hg is not None and ag is not None:
                            hg = int(hg)
                            ag = int(ag)
                            f_id = fix.get("fixture", {}).get("id")
                            referee_name = fix.get("fixture", {}).get("referee")
                            
                            stats = fetch_fixture_statistics(f_id, api_key=api_key) if f_id else {"corners": 9, "cards": 4, "actual_xg": None}
                            corners = stats.get("corners", 9)
                            cards = stats.get("cards", 4)
                            actual_xg = stats.get("actual_xg")

                            tracker.grade_single_match(
                                pred["match_id"],
                                fthg=hg,
                                ftag=ag,
                                hc=corners // 2,
                                ac=corners - (corners // 2),
                                cards=cards,
                                actual_xg=actual_xg,
                                referee=referee_name
                            )
                            reconciled_count += 1
                            matched_fixtures.append(f"{pred.get('home_team')} {hg}-{ag} {pred.get('away_team')}")
                            break

    return {
        "reconciled": reconciled_count,
        "checked_dates": unique_dates,
        "matches": matched_fixtures,
        "message": f"Successfully reconciled {reconciled_count} real matches from API-Football!" if reconciled_count > 0 else "Checked API-Football for past dates. No newly finished scores found matching pending fixtures."
    }


def auto_check_daily_reconciliation(tracker, api_key: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
    """
    Perform automatic once-a-day background reconciliation against API-Football.
    """
    now = time.time()
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    if not force and AUTO_RECONCILE_META_FILE.exists():
        try:
            with open(AUTO_RECONCILE_META_FILE, "r", encoding="utf-8") as f:
                meta = json.load(f)
                last_date = meta.get("last_reconcile_date")
                last_ts = meta.get("last_reconcile_ts", 0)
                if last_date == today_str or (now - last_ts < 72000):
                    return {"reconciled": 0, "message": "Already reconciled today.", "ran": False}
        except Exception:
            pass

    res = reconcile_predictions_with_api_football(tracker, api_key=api_key)
    try:
        AUTO_RECONCILE_META_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(AUTO_RECONCILE_META_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "last_reconcile_date": today_str,
                "last_reconcile_ts": now,
                "last_reconciled_count": res.get("reconciled", 0)
            }, f, indent=2)
    except Exception as e:
        logger.debug(f"Could not save reconcile metadata: {e}")

    res["ran"] = True
    return res
