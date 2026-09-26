"""ESPN public API client for fetching 100% real upcoming football match schedules,
live market odds (DraftKings/consensus converted to decimal), and official match results.
Completely free, no authentication needed, zero hallucinations.
"""
import json
import logging
import math
import subprocess
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import requests

from football_core.config import CACHE_DIR, LEAGUES
from football_core.utils.helpers import normalize_team_name, teams_match, strip_accents

logger = logging.getLogger(__name__)

ESPN_BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer"

# Mapping project league keys to ESPN soccer competition codes
ESPN_LEAGUE_CODES = {
    "EPL": "eng.1",
    "LaLiga": "esp.1",
    "SerieA": "ita.1",
    "Bundesliga": "ger.1",
    "Ligue1": "fra.1",
    "Eredivisie": "ned.1",
    "PrimeiraLiga": "por.1",
    "Belgium": "bel.1",
    "ScottishPrem": "sco.1",
    "UCL": "uefa.champions",
    "UEL": "uefa.europa",
    "UECL": "uefa.europa.conf",
    # 10 International Competitions
    "NationsLeague": "uefa.nations",
    "WorldCup": "fifa.world",
    "WCQ_UEFA": "fifa.worldq.uefa",
    "WCQ_CONMEBOL": "fifa.worldq.conmebol",
    "WCQ_CAF": "fifa.worldq.caf",
    "Euro": "uefa.euro",
    "CopaAmerica": "conmebol.america",
    "AFCON": "caf.nations",
    "Friendlies": "fifa.friendly",
    "GoldCup": "concacaf.gold",
}


def _espn_get_json(url: str, params: Optional[Dict] = None) -> Optional[Dict]:
    """Reliably query ESPN API using requests with curl-fallback."""
    query_str = ""
    if params:
        query_str = "?" + "&".join(f"{k}={v}" for k, v in params.items())
    full_url = f"{url}{query_str}"
    
    # 1. Direct request with clean curl User-Agent
    try:
        r = requests.get(full_url, headers={"User-Agent": "curl/8.5.0", "Accept": "*/*"}, timeout=12)
        if r.status_code == 200:
            return r.json()
        elif r.status_code in (403, 404):
            return None
    except Exception:
        pass

    # 2. Curl fallback
    try:
        cmd = ["curl", "-sL", "--compressed", "-A", "curl/8.5.0", full_url]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if res.returncode == 0 and res.stdout.strip().startswith("{"):
            return json.loads(res.stdout)
    except Exception as e:
        logger.warning(f"Curl fallback failed for {full_url}: {e}")

    return None


def american_to_decimal(american_odds: Any) -> Optional[float]:
    """Convert American moneyline odds (e.g. +125, -140) to European decimal odds (e.g. 2.25, 1.71).
    Also safely handles 'EVEN' / 'EV', values already in decimal format (e.g. 2.25), and invalid strings.
    """
    if american_odds is None:
        return None
    val_str = str(american_odds).strip().replace("−", "-")
    if not val_str:
        return None
    if val_str.upper() in ("EVEN", "EV", "PK", "PICK"):
        return 2.00
    try:
        val = float(val_str)
        if not math.isfinite(val):
            return None
        if val == 0:
            return None
        # Check if already in decimal format (typically 1.01 to 99.0, American odds are never in (-100, 100))
        if 1.01 <= val < 100.0 and not val_str.startswith("+"):
            return round(val, 2)
        if val >= 100.0:
            return round(1.0 + (val / 100.0), 2)
        elif val <= -100.0:
            return round(1.0 + (100.0 / abs(val)), 2)
        elif val >= 1.01:
            return round(val, 2)
        return None
    except (ValueError, TypeError):
        return None


def fetch_espn_upcoming_fixtures(league_key: str, days_ahead: int = 14) -> List[Dict[str, Any]]:
    """Fetch real scheduled upcoming matches and market odds for a league from ESPN API."""
    league_info = LEAGUES.get(league_key, {})
    espn_code = league_info.get("espn_code") or ESPN_LEAGUE_CODES.get(league_key)
    if not espn_code:
        return []

    url = f"{ESPN_BASE_URL}/{espn_code}/scoreboard"
    events_map = {}
    now = datetime.now(timezone.utc)
    is_cup_or_intl = bool(league_info.get("is_cup") or league_info.get("is_international") or league_key in ["UCL", "UEL", "UECL"])
    check_days = max(days_ahead, 45 if is_cup_or_intl else days_ahead)

    # 1. Date range query (fetches entire upcoming window in a single request)
    start_d = now.strftime("%Y%m%d")
    end_d = (now + timedelta(days=check_days)).strftime("%Y%m%d")
    range_data = _espn_get_json(url, {"dates": f"{start_d}-{end_d}"})
    if range_data and "events" in range_data:
        for ev in range_data["events"]:
            ev_id = ev.get("id")
            if ev_id:
                events_map[ev_id] = ev

    # 2. Check default scoreboard (covers current round/gameday) if range returned nothing
    if not events_map:
        d0 = _espn_get_json(url)
        if d0 and "events" in d0:
            for ev in d0["events"]:
                ev_id = ev.get("id")
                if ev_id:
                    events_map[ev_id] = ev

    # 3. Fallback day-by-day query if range returned nothing and window is short
    if not events_map and check_days <= 14:
        for day_offset in range(check_days):
            day_str = (now + timedelta(days=day_offset)).strftime("%Y%m%d")
            d_day = _espn_get_json(url, {"dates": day_str})
            if d_day and "events" in d_day:
                for ev in d_day["events"]:
                    ev_id = ev.get("id")
                    if ev_id:
                        events_map[ev_id] = ev

    events = list(events_map.values())
    if not events:
        return []
    fixtures = []

    for e in events:
        competitions = e.get("competitions") or []
        if not competitions or not isinstance(competitions[0], dict):
            continue
        comp = competitions[0]
        status_info = (comp.get("status") or {}).get("type") or {}
        if status_info.get("completed", False):
            continue  # Skip finished games

        competitors = comp.get("competitors", [])
        if len(competitors) < 2:
            continue

        home_c = competitors[0] if competitors[0].get("homeAway") == "home" else competitors[1]
        away_c = competitors[1] if competitors[1].get("homeAway") == "away" else competitors[0]

        home_raw = (home_c.get("team") or {}).get("displayName", "")
        away_raw = (away_c.get("team") or {}).get("displayName", "")
        if not home_raw or not away_raw:
            continue

        home_norm = normalize_team_name(home_raw)
        away_norm = normalize_team_name(away_raw)

        date_iso = e.get("date", "")
        date_str = date_iso[:10] if date_iso else now.strftime("%Y-%m-%d")

        # Extract Referee if available
        referee_name = None
        officials = comp.get("officials", [])
        if officials:
            referee_name = officials[0].get("displayName")

        # Extract Market Odds (DraftKings consensus) with comprehensive fallbacks
        odds_list = comp.get("odds", [])
        odds_h = None
        odds_d = None
        odds_a = None
        odds_o25 = None
        odds_u25 = None

        if odds_list and isinstance(odds_list[0], dict):
            o_item = odds_list[0]
            ml = o_item.get("moneyline") or {}
            if isinstance(ml, dict) and ml:
                odds_h = american_to_decimal(
                    ((ml.get("home") or {}).get("close") or {}).get("odds")
                    or ((ml.get("home") or {}).get("open") or {}).get("odds")
                )
                odds_d = american_to_decimal(
                    ((ml.get("draw") or {}).get("close") or {}).get("odds")
                    or ((ml.get("draw") or {}).get("open") or {}).get("odds")
                )
                odds_a = american_to_decimal(
                    ((ml.get("away") or {}).get("close") or {}).get("odds")
                    or ((ml.get("away") or {}).get("open") or {}).get("odds")
                )
            
            # Moneyline fallbacks when ml is sparse
            if odds_h is None and o_item.get("homeTeamOdds"):
                ht_odds = o_item.get("homeTeamOdds")
                if isinstance(ht_odds, dict):
                    odds_h = american_to_decimal(
                        ht_odds.get("moneyLine")
                        or (ht_odds.get("close") or {}).get("odds")
                        or ht_odds.get("odds")
                    )
                else:
                    odds_h = american_to_decimal(ht_odds)
            if odds_a is None and o_item.get("awayTeamOdds"):
                at_odds = o_item.get("awayTeamOdds")
                if isinstance(at_odds, dict):
                    odds_a = american_to_decimal(
                        at_odds.get("moneyLine")
                        or (at_odds.get("close") or {}).get("odds")
                        or at_odds.get("odds")
                    )
                else:
                    odds_a = american_to_decimal(at_odds)
            if odds_d is None and o_item.get("drawOdds"):
                dr_odds = o_item.get("drawOdds")
                if isinstance(dr_odds, dict):
                    odds_d = american_to_decimal(
                        dr_odds.get("moneyLine")
                        or (dr_odds.get("close") or {}).get("odds")
                        or dr_odds.get("odds")
                    )
                else:
                    odds_d = american_to_decimal(dr_odds)

            tot = o_item.get("total") or {}
            if isinstance(tot, dict) and tot:
                odds_o25 = american_to_decimal(
                    ((tot.get("over") or {}).get("close") or {}).get("odds")
                    or ((tot.get("over") or {}).get("open") or {}).get("odds")
                )
                odds_u25 = american_to_decimal(
                    ((tot.get("under") or {}).get("close") or {}).get("odds")
                    or ((tot.get("under") or {}).get("open") or {}).get("odds")
                )

            # Totals fallbacks when tot is sparse
            if odds_o25 is None and o_item.get("overOdds") is not None:
                o_odds = o_item.get("overOdds")
                if isinstance(o_odds, dict):
                    odds_o25 = american_to_decimal(
                        o_odds.get("moneyLine")
                        or (o_odds.get("close") or {}).get("odds")
                        or o_odds.get("odds")
                    )
                else:
                    odds_o25 = american_to_decimal(o_odds)
            if odds_u25 is None and o_item.get("underOdds") is not None:
                u_odds = o_item.get("underOdds")
                if isinstance(u_odds, dict):
                    odds_u25 = american_to_decimal(
                        u_odds.get("moneyLine")
                        or (u_odds.get("close") or {}).get("odds")
                        or u_odds.get("odds")
                    )
                else:
                    odds_u25 = american_to_decimal(u_odds)

        match_id = f"{league_key}_{home_norm}_{away_norm}_{date_str}".replace(" ", "_")

        fixtures.append({
            "match_id": match_id,
            "espn_id": e.get("id"),
            "league": league_key,
            "league_name": league_info.get("name", league_key),
            "flag": league_info.get("flag", "⚽"),
            "date": date_str,
            "commence_time": date_iso,
            "home_team": home_norm,
            "away_team": away_norm,
            "referee": referee_name,
            "is_neutral": bool(comp.get("neutralSite", False)),
            "bookmaker": "DraftKings (ESPN)",
            "odds_home": odds_h,
            "odds_draw": odds_d,
            "odds_away": odds_a,
            "odds_over25": odds_o25,
            "odds_under25": odds_u25,
            "odds_btts_yes": None,
            "odds_btts_no": None,
            "odds_corners_over95": None,
            "odds_corners_under95": None,
            "odds_cards_over35": None,
            "odds_cards_under35": None,
            "is_real_schedule": True,
        })

    logger.info(f"Fetched {len(fixtures)} real upcoming fixtures for {league_key} from ESPN")
    return fixtures


def fetch_espn_completed_matches(league_key: str, days_back: int = 14) -> List[Dict[str, Any]]:
    """Fetch completed matches and official scores for a league from ESPN API."""
    espn_code = LEAGUES.get(league_key, {}).get("espn_code") or ESPN_LEAGUE_CODES.get(league_key)
    if not espn_code:
        return []

    url = f"{ESPN_BASE_URL}/{espn_code}/scoreboard"
    now = datetime.now(timezone.utc)
    start_ts = now.timestamp() - (days_back * 86400)
    start_d = datetime.fromtimestamp(start_ts, timezone.utc).strftime("%Y%m%d")
    end_d = now.strftime("%Y%m%d")

    data = _espn_get_json(url, {"dates": f"{start_d}-{end_d}"})
    if not data:
        return []

    events = data.get("events", [])
    completed = []

    for e in events:
        competitions = e.get("competitions") or []
        if not competitions or not isinstance(competitions[0], dict):
            continue
        comp = competitions[0]
        status_info = (comp.get("status") or {}).get("type") or {}
        if not status_info.get("completed", False):
            continue

        competitors = comp.get("competitors", [])
        if len(competitors) < 2:
            continue

        home_c = competitors[0] if competitors[0].get("homeAway") == "home" else competitors[1]
        away_c = competitors[1] if competitors[1].get("homeAway") == "away" else competitors[0]

        home_raw = (home_c.get("team") or {}).get("displayName", "")
        away_raw = (away_c.get("team") or {}).get("displayName", "")
        if not home_raw or not away_raw:
            continue

        h_team = normalize_team_name(home_raw)
        a_team = normalize_team_name(away_raw)
        
        try:
            h_score = int(home_c.get("score", 0))
            a_score = int(away_c.get("score", 0))
        except (ValueError, TypeError):
            continue

        date_iso = e.get("date", "")
        date_str = date_iso[:10] if date_iso else now.strftime("%Y-%m-%d")

        # Referee
        referee_name = None
        officials = comp.get("officials", [])
        if officials:
            referee_name = officials[0].get("displayName")

        winner = "Draw"
        if h_score > a_score:
            winner = h_team
        elif a_score > h_score:
            winner = a_team

        completed.append({
            "league": league_key,
            "date": date_str,
            "home_team": h_team,
            "away_team": a_team,
            "home_score": h_score,
            "away_score": a_score,
            "score": f"{h_score}-{a_score}",
            "winner": winner,
            "referee": referee_name,
        })

    return completed


def fetch_espn_event_boxscore(espn_code: str, event_id: str) -> Dict[str, Any]:
    """Fetch boxscore statistics (corners, cards) for a completed match from ESPN."""
    url = f"{ESPN_BASE_URL}/{espn_code}/summary"
    data = _espn_get_json(url, {"event": event_id})
    if not data or "boxscore" not in data:
        return {}
    teams = data.get("boxscore", {}).get("teams", [])
    total_corners = 0
    total_cards = 0
    has_stats = False
    hc = 0
    ac = 0
    for idx, t in enumerate(teams):
        stats = {s.get("name"): s.get("displayValue") for s in t.get("statistics", [])}
        corn = int(stats.get("wonCorners") or 0)
        cards = int(stats.get("yellowCards") or 0) + int(stats.get("redCards") or 0)
        if "wonCorners" in stats or "yellowCards" in stats:
            has_stats = True
        if idx == 0:
            hc = corn
        else:
            ac = corn
        total_corners += corn
        total_cards += cards

    if not has_stats:
        return {}

    return {
        "corners": total_corners,
        "hc": hc,
        "ac": ac,
        "cards": total_cards
    }


def reconcile_tracker_with_espn(tracker) -> int:
    """Reconcile pending predictions against ESPN's public finished match scorecards.
    100% free, no authentication needed, and no historical date restrictions.
    """
    pending = [p for p in tracker.predictions if p.get("status") in ("pending", "Pending", None)]
    if not pending:
        return 0

    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")

    # Group pending predictions by (espn_code, date)
    to_query = set()
    for p in pending:
        p_date = (p.get("date") or "")[:10]
        if not p_date or p_date > today_str:
            continue
        l_k = p.get("league_key") or p.get("league")
        espn_code = ESPN_LEAGUE_CODES.get(l_k)
        if not espn_code:
            for k, code in ESPN_LEAGUE_CODES.items():
                if k.lower() in str(l_k).lower():
                    espn_code = code
                    break
        if espn_code:
            try:
                base_dt = datetime.strptime(p_date, "%Y-%m-%d")
                for offset in [-1, 0, 1]:
                    dt_check = base_dt + timedelta(days=offset)
                    if dt_check.strftime("%Y-%m-%d") <= today_str:
                        to_query.add((espn_code, dt_check.strftime("%Y%m%d")))
            except Exception:
                to_query.add((espn_code, p_date.replace("-", "")))

    if not to_query:
        return 0

    reconciled = 0
    completed_events = []
    for espn_code, d_clean in to_query:
        url = f"{ESPN_BASE_URL}/{espn_code}/scoreboard"
        data = _espn_get_json(url, {"dates": d_clean})
        if not data:
            continue
        for e in data.get("events", []):
            competitions = e.get("competitions") or []
            if not competitions or not isinstance(competitions[0], dict):
                continue
            comp = competitions[0]
            if not (comp.get("status") or {}).get("type", {}).get("completed", False):
                continue
            competitors = comp.get("competitors", [])
            if len(competitors) < 2:
                continue
            home_c = competitors[0] if competitors[0].get("homeAway") == "home" else competitors[1]
            away_c = competitors[1] if competitors[1].get("homeAway") == "away" else competitors[0]
            home_raw = (home_c.get("team") or {}).get("displayName", "")
            away_raw = (away_c.get("team") or {}).get("displayName", "")
            try:
                hs = int(home_c.get("score", 0))
                as_ = int(away_c.get("score", 0))
            except Exception:
                continue
            referee_name = None
            officials = comp.get("officials", [])
            if officials:
                referee_name = officials[0].get("displayName")
            completed_events.append({
                "event_id": e.get("id"),
                "espn_code": espn_code,
                "home": home_raw,
                "away": away_raw,
                "h_score": hs,
                "a_score": as_,
                "referee": referee_name
            })

    # Grade matching pending predictions
    boxscore_cache = {}
    for pred in pending:
        p_h = pred.get("home_team", "")
        p_a = pred.get("away_team", "")
        for ev in completed_events:
            h_match = (
                teams_match(p_h, ev["home"]) 
                or teams_match(normalize_team_name(p_h), normalize_team_name(ev["home"]))
                or strip_accents(p_h) in strip_accents(ev["home"])
                or strip_accents(ev["home"]) in strip_accents(p_h)
            )
            a_match = (
                teams_match(p_a, ev["away"]) 
                or teams_match(normalize_team_name(p_a), normalize_team_name(ev["away"]))
                or strip_accents(p_a) in strip_accents(ev["away"])
                or strip_accents(ev["away"]) in strip_accents(p_a)
            )
            if h_match and a_match:
                event_id = ev.get("event_id")
                espn_code = ev.get("espn_code")
                box = {}
                if event_id and espn_code:
                    if event_id not in boxscore_cache:
                        boxscore_cache[event_id] = fetch_espn_event_boxscore(espn_code, event_id)
                    box = boxscore_cache[event_id]

                hc = box.get("hc")
                ac = box.get("ac")
                cards = box.get("cards")

                graded = tracker.grade_single_match(
                    match_id=pred["match_id"],
                    fthg=ev["h_score"],
                    ftag=ev["a_score"],
                    hc=hc,
                    ac=ac,
                    cards=cards,
                    referee=ev["referee"]
                )
                if graded:
                    reconciled += 1
                break

    if reconciled > 0:
        tracker.save()
        logger.info(f"ESPN auto-reconciled and graded {reconciled} matches.")
    return reconciled


def backfill_missing_corners_cards(tracker) -> int:
    """Scan all settled predictions that have missing actual_corners or actual_cards,
    and enrich them with official corner/card statistics from ESPN boxscore summaries.
    """
    missing = [
        p for p in tracker.predictions 
        if p.get("status") == "settled" and (p.get("actual_corners") is None or p.get("actual_cards") is None)
    ]
    if not missing:
        return 0

    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")

    # Group missing predictions by (espn_code, date)
    to_query = set()
    for p in missing:
        p_date = (p.get("date") or "")[:10]
        if not p_date:
            continue
        l_k = p.get("league_key") or p.get("league")
        espn_code = ESPN_LEAGUE_CODES.get(l_k)
        if not espn_code:
            for k, code in ESPN_LEAGUE_CODES.items():
                if k.lower() in str(l_k).lower():
                    espn_code = code
                    break
        if espn_code:
            try:
                base_dt = datetime.strptime(p_date, "%Y-%m-%d")
                for offset in [-1, 0, 1]:
                    dt_check = base_dt + timedelta(days=offset)
                    to_query.add((espn_code, dt_check.strftime("%Y%m%d")))
            except Exception:
                to_query.add((espn_code, p_date.replace("-", "")))

    if not to_query:
        return 0

    # Query scoreboards
    completed_events = []
    for espn_code, d_clean in to_query:
        url = f"{ESPN_BASE_URL}/{espn_code}/scoreboard"
        data = _espn_get_json(url, {"dates": d_clean})
        if not data:
            continue
        for e in data.get("events", []):
            competitions = e.get("competitions") or []
            if not competitions or not isinstance(competitions[0], dict):
                continue
            comp = competitions[0]
            if not (comp.get("status") or {}).get("type", {}).get("completed", False):
                continue
            competitors = comp.get("competitors", [])
            if len(competitors) < 2:
                continue
            home_c = competitors[0] if competitors[0].get("homeAway") == "home" else competitors[1]
            away_c = competitors[1] if competitors[1].get("homeAway") == "away" else competitors[0]
            home_raw = (home_c.get("team") or {}).get("displayName", "")
            away_raw = (away_c.get("team") or {}).get("displayName", "")
            referee_name = None
            officials = comp.get("officials", [])
            if officials:
                referee_name = officials[0].get("displayName")

            completed_events.append({
                "event_id": e.get("id"),
                "espn_code": espn_code,
                "home": home_raw,
                "away": away_raw,
                "referee": referee_name
            })

    boxscore_cache = {}
    backfilled = 0

    for pred in missing:
        p_h = pred.get("home_team", "")
        p_a = pred.get("away_team", "")
        for ev in completed_events:
            h_match = (
                teams_match(p_h, ev["home"]) 
                or teams_match(normalize_team_name(p_h), normalize_team_name(ev["home"]))
                or strip_accents(p_h) in strip_accents(ev["home"])
                or strip_accents(ev["home"]) in strip_accents(p_h)
            )
            a_match = (
                teams_match(p_a, ev["away"]) 
                or teams_match(normalize_team_name(p_a), normalize_team_name(ev["away"]))
                or strip_accents(p_a) in strip_accents(ev["away"])
                or strip_accents(ev["away"]) in strip_accents(p_a)
            )
            if h_match and a_match:
                event_id = ev.get("event_id")
                espn_code = ev.get("espn_code")
                if not event_id or not espn_code:
                    break

                if event_id not in boxscore_cache:
                    boxscore_cache[event_id] = fetch_espn_event_boxscore(espn_code, event_id)

                box = boxscore_cache[event_id]
                if box and "corners" in box and "cards" in box:
                    actual_corners = int(box["corners"])
                    actual_cards = int(box["cards"])

                    pred["actual_corners"] = actual_corners
                    pred_corn = pred.get("pred_corners_o95", "Over 9.5")
                    actual_corn_str = "Over 9.5" if actual_corners > 9.5 else "Under 9.5"
                    pred["correct_corners_o95"] = bool(pred_corn == actual_corn_str)
                    pred["corner_error"] = round(abs(float(pred.get("exp_corners", 9.5)) - actual_corners), 2)

                    pred["actual_cards"] = actual_cards
                    pred_cards = pred.get("pred_cards_o35", "Over 3.5")
                    actual_cards_str = "Over 3.5" if actual_cards > 3.5 else "Under 3.5"
                    pred["correct_cards_o35"] = bool(pred_cards == actual_cards_str)
                    pred["card_error"] = round(abs(float(pred.get("exp_cards", 4.2)) - actual_cards), 2)

                    if ev.get("referee") and (not pred.get("referee") or "Unassigned" in pred.get("referee", "")):
                        pred["referee"] = ev["referee"]

                    backfilled += 1
                break

    if backfilled > 0:
        tracker.save()
        logger.info(f"ESPN backfilled corner and card statistics for {backfilled} settled matches.")

    return backfilled

