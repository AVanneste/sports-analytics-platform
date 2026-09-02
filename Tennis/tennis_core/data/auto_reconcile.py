"""Automated Daily Tennis Results Reconciliation Engine (The Odds API Scores & Tennis-Data.co.uk)."""
import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pandas as pd
import requests

from tennis_core.config import UPCOMING_DATA_DIR, RAW_DATA_DIR
from tennis_core.data.odds_api import DEFAULT_ODDS_API_KEY
from tennis_core.utils.helpers import strip_accents, normalize_player_name

logger = logging.getLogger(__name__)

TENNIS_AUTO_RECONCILE_META = UPCOMING_DATA_DIR / "auto_reconcile_meta.json"

TENNIS_SPORTS_KEYS = [
    "tennis_atp_us_open",
    "tennis_wta_us_open",
    "tennis_atp_aus_open",
    "tennis_wta_aus_open",
    "tennis_atp_french_open",
    "tennis_wta_french_open",
    "tennis_atp_wimbledon",
    "tennis_wta_wimbledon",
    "tennis_atp_indian_wells",
    "tennis_wta_indian_wells",
    "tennis_atp_miami_open",
    "tennis_wta_miami_open",
    "tennis_atp_madrid_open",
    "tennis_wta_madrid_open",
    "tennis_atp_italian_open",
    "tennis_wta_italian_open",
    "tennis_atp_canadian_open",
    "tennis_wta_canadian_open",
    "tennis_atp_cincinnati_open",
    "tennis_wta_cincinnati_open",
    "tennis_atp_shanghai_masters",
    "tennis_atp_paris_masters",
    "tennis_atp_atp_finals",
    "tennis_wta_wta_finals",
]


def fetch_odds_api_tennis_scores(api_key: str = DEFAULT_ODDS_API_KEY, days_from: int = 3) -> List[Dict]:
    """Fetch completed match scores from The Odds API for all active Grand Slams and Masters."""
    completed_matches = []
    if not api_key:
        return []

    for sport_key in TENNIS_SPORTS_KEYS:
        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/scores/?apiKey={api_key}&daysFrom={days_from}"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for m in data:
                    if m.get("completed"):
                        completed_matches.append(m)
        except Exception as e:
            logger.debug(f"Could not fetch scores for {sport_key}: {e}")

    return completed_matches


def reconcile_from_odds_api(tracker, api_key: str = DEFAULT_ODDS_API_KEY) -> Tuple[int, List[str]]:
    """
    Reconcile pending tennis predictions against real finished scores from The Odds API.
    NEVER simulates or assumes results.
    """
    completed_odds_matches = fetch_odds_api_tennis_scores(api_key=api_key, days_from=3)
    if not completed_odds_matches:
        return 0, []

    reconciled_count = 0
    reconciled_matches = []

    for m in completed_odds_matches:
        scores = m.get("scores", [])
        if not scores or len(scores) < 2:
            continue

        try:
            pA = scores[0].get("name", "")
            sA = int(scores[0].get("score", 0))
            pB = scores[1].get("name", "")
            sB = int(scores[1].get("score", 0))
        except (ValueError, TypeError):
            continue

        if sA == sB:
            continue

        winner_raw = pA if sA > sB else pB
        score_str = f"{sA}-{sB}" if winner_raw == pA else f"{sB}-{sA}"

        for pred in tracker.predictions:
            if pred.get("status") != "PENDING":
                continue

            p1 = pred.get("p1_name", "")
            p2 = pred.get("p2_name", "")

            # Match check
            p1_in = (strip_accents(p1).lower() in strip_accents(pA).lower() or strip_accents(pA).lower() in strip_accents(p1).lower() or
                     strip_accents(p1).lower() in strip_accents(pB).lower() or strip_accents(pB).lower() in strip_accents(p1).lower())
            p2_in = (strip_accents(p2).lower() in strip_accents(pA).lower() or strip_accents(pA).lower() in strip_accents(p2).lower() or
                     strip_accents(p2).lower() in strip_accents(pB).lower() or strip_accents(pB).lower() in strip_accents(p2).lower())

            if p1_in and p2_in:
                winner_resolved = p1 if (strip_accents(p1).lower() in strip_accents(winner_raw).lower() or strip_accents(winner_raw).lower() in strip_accents(p1).lower()) else p2
                tracker.grade_match(pred["match_id"], actual_winner=winner_resolved, score=score_str)
                reconciled_count += 1
                reconciled_matches.append(f"{p1} vs {p2} -> {winner_resolved} ({score_str})")

    return reconciled_count, reconciled_matches


def reconcile_from_tennis_data_sheets(tracker) -> int:
    """Download 2026 ATP/WTA sheets from tennis-data.co.uk and reconcile any pending matches."""
    try:
        from tennis_core.data.fetcher import download_tennis_data_year
        from tennis_core.data.preprocessor import load_raw_matches, clean_match_data
        curr_year = datetime.now().year
        download_tennis_data_year("atp", curr_year, force=False)
        download_tennis_data_year("wta", curr_year, force=False)
        
        df_atp = clean_match_data(load_raw_matches("atp"), "atp")
        df_wta = clean_match_data(load_raw_matches("wta"), "wta")
        df_combined = pd.concat([df_atp, df_wta], ignore_index=True) if (not df_atp.empty or not df_wta.empty) else pd.DataFrame()
        if not df_combined.empty:
            return tracker.auto_reconcile(df_combined)
    except Exception as e:
        logger.warning(f"Error checking tennis-data.co.uk sheets: {e}")
    return 0


def auto_check_daily_tennis_reconciliation(tracker, force: bool = False) -> Dict[str, Any]:
    """
    Run automated tennis reconciliation once per day.
    Queries The Odds API scores and tennis-data.co.uk.
    Strictly reports unverified matches as warnings without generating fake results.
    """
    today_str = date.today().isoformat()
    
    # Check meta to limit to 1 automatic query per day unless forced
    if not force and TENNIS_AUTO_RECONCILE_META.exists():
        try:
            with open(TENNIS_AUTO_RECONCILE_META, "r", encoding="utf-8") as f:
                meta = json.load(f)
                if meta.get("last_check_date") == today_str and meta.get("status") == "success":
                    # Already checked today
                    pending_past = [
                        p for p in tracker.predictions
                        if p.get("status") == "PENDING" and p.get("date") and str(p.get("date"))[:10] < today_str
                    ]
                    return {
                        "checked_today": True,
                        "reconciled": 0,
                        "pending_past_unverified": len(pending_past),
                        "pending_matches": [f"{p.get('p1_name')} vs {p.get('p2_name')} ({p.get('date')})" for p in pending_past],
                        "message": "Already checked for new results today."
                    }
        except Exception:
            pass

    # 1. Reconcile from The Odds API scores
    reconciled_odds, rec_list = reconcile_from_odds_api(tracker)

    # 2. Reconcile from tennis-data.co.uk sheets
    reconciled_sheets = reconcile_from_tennis_data_sheets(tracker)

    total_reconciled = reconciled_odds + reconciled_sheets

    # 3. Find past matches that are still pending
    pending_past = [
        p for p in tracker.predictions
        if p.get("status") == "PENDING" and p.get("date") and str(p.get("date"))[:10] < today_str
    ]

    # Save meta
    TENNIS_AUTO_RECONCILE_META.parent.mkdir(parents=True, exist_ok=True)
    with open(TENNIS_AUTO_RECONCILE_META, "w", encoding="utf-8") as f:
        json.dump({
            "last_check_date": today_str,
            "last_check_timestamp": datetime.now().isoformat(),
            "total_reconciled": total_reconciled,
            "pending_past_unverified": len(pending_past),
            "status": "success"
        }, f, indent=2)

    return {
        "checked_today": True,
        "reconciled": total_reconciled,
        "reconciled_details": rec_list,
        "pending_past_unverified": len(pending_past),
        "pending_matches": [f"{p.get('p1_name')} vs {p.get('p2_name')} ({p.get('date')})" for p in pending_past],
        "message": f"Auto-reconciled {total_reconciled} matches today."
    }
