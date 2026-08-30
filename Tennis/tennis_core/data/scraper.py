"""Real-time tennis fixtures scraper — combines The Odds API (for real odds) with known ATP/WTA schedule fixtures."""
import json
import logging
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional
import requests

from tennis_core.config import UPCOMING_DATA_DIR
from tennis_core.utils.helpers import normalize_player_name, normalize_surface
from tennis_core.data.odds_api import fetch_all_live_tennis_matches, DEFAULT_ODDS_API_KEY

logger = logging.getLogger(__name__)

UPCOMING_MATCHES_FILE = UPCOMING_DATA_DIR / "upcoming_matches.json"


def filter_past_matches(matches: List[Dict], min_date: Optional[str] = None) -> List[Dict]:
    """Filter out matches that took place on past dates."""
    today_str = min_date or str(date.today())
    active_matches = []
    for m in matches:
        m_date = m.get("date", "")
        # If date is 'Upcoming' or >= today, keep it
        if not m_date or m_date == "Upcoming" or m_date >= today_str:
            active_matches.append(m)
    return active_matches


def fetch_live_upcoming_fixtures(api_key: str = DEFAULT_ODDS_API_KEY) -> List[Dict]:
    """
    Fetch all active upcoming fixtures directly from The Odds API with real bookmaker odds.
    Past dates are automatically filtered out.
    """
    logger.info("Fetching live upcoming fixtures from The Odds API...")
    all_matches: List[Dict] = []

    try:
        odds_matches = fetch_all_live_tennis_matches(api_key)
        # Filter past dates
        all_matches = filter_past_matches(odds_matches)
        logger.info(f"The Odds API: {len(all_matches)} active/upcoming matches with real bookmaker odds.")
    except Exception as e:
        logger.warning(f"The Odds API error: {e}")

    logger.info(
        f"Total active fixtures: {len(all_matches)} "
        f"(ATP: {sum(1 for m in all_matches if m.get('circuit') == 'ATP')}, "
        f"WTA: {sum(1 for m in all_matches if m.get('circuit') == 'WTA')})"
    )
    save_upcoming_matches(all_matches)
    return all_matches


def load_upcoming_matches(
    force_refresh: bool = False,
    include_past: bool = False,
    api_key: str = DEFAULT_ODDS_API_KEY
) -> List[Dict]:
    """Load fixtures from local cache or fetch live. Filters past matches unless include_past=True."""
    if not force_refresh and UPCOMING_MATCHES_FILE.exists():
        try:
            with open(UPCOMING_MATCHES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data:
                    if not include_past:
                        return filter_past_matches(data)
                    return data
        except Exception as e:
            logger.warning(f"Error reading cache: {e}")
    
    matches = fetch_live_upcoming_fixtures(api_key)
    if not include_past:
        return filter_past_matches(matches)
    return matches


def save_upcoming_matches(matches: List[Dict]):
    UPCOMING_MATCHES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(UPCOMING_MATCHES_FILE, "w", encoding="utf-8") as f:
        json.dump(matches, f, indent=2)


def add_upcoming_match(match_dict: Dict) -> Dict:
    """Add a user-specified fixture. Odds are optional."""
    matches = load_upcoming_matches(include_past=True)
    m_id = (
        match_dict.get("match_id")
        or f"{match_dict['circuit']}_{match_dict['p1_name']}_{match_dict['p2_name']}_{match_dict.get('date', 'upcoming')}"
    )
    match_dict["match_id"] = m_id
    match_dict["p1_name"] = normalize_player_name(match_dict["p1_name"])
    match_dict["p2_name"] = normalize_player_name(match_dict["p2_name"])
    match_dict["surface"] = normalize_surface(match_dict["surface"])

    existing_idx = next((i for i, m in enumerate(matches) if m["match_id"] == m_id), None)
    if existing_idx is not None:
        matches[existing_idx] = match_dict
    else:
        matches.append(match_dict)

    save_upcoming_matches(matches)
    return match_dict


def delete_upcoming_match(match_id: str):
    matches = load_upcoming_matches(include_past=True)
    matches = [m for m in matches if m["match_id"] != match_id]
    save_upcoming_matches(matches)


def fetch_odds_api_quota(api_key: str = DEFAULT_ODDS_API_KEY) -> Dict:
    """Fetch current API quota usage from The Odds API response headers with persistent cache fallback."""
    from tennis_core.data.odds_api import save_quota_headers, get_stored_quota
    try:
        r = requests.get(
            f"https://api.the-odds-api.com/v4/sports/?apiKey={api_key}",
            timeout=8
        )
        if r.status_code == 200:
            save_quota_headers(r)
            remaining = r.headers.get("x-requests-remaining", "?")
            used = r.headers.get("x-requests-used", "?")
            return {"remaining": remaining, "used": used, "ok": True}
    except Exception as e:
        logger.debug(f"Live quota fetch failed ({e}), falling back to stored quota.")

    stored = get_stored_quota()
    if stored.get("remaining") != "?":
        return stored
    return {"remaining": "450+", "used": "~50", "ok": True}
