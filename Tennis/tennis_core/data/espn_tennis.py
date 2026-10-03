"""ESPN API client for fetching real upcoming tennis tournament fixtures and matches,
and reconciling predictions against official completed match outcomes.
"""
import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import requests

from tennis_core.config import UPCOMING_DATA_DIR
from tennis_core.utils.helpers import normalize_player_name, normalize_surface, strip_accents

logger = logging.getLogger(__name__)

ESPN_TENNIS_BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/tennis"


def _espn_tennis_get(url: str, params: Optional[Dict] = None) -> Optional[Dict]:
    """Query ESPN Tennis endpoint using clean headers and curl fallback."""
    query_str = ""
    if params:
        query_str = "?" + "&".join(f"{k}={v}" for k, v in params.items())
    full_url = f"{url}{query_str}"

    try:
        r = requests.get(full_url, headers={"User-Agent": "curl/8.5.0", "Accept": "*/*"}, timeout=12)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass

    try:
        cmd = ["curl", "-sL", "--compressed", "-A", "curl/8.5.0", full_url]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if res.returncode == 0 and res.stdout.strip().startswith("{"):
            return json.loads(res.stdout)
    except Exception as e:
        logger.warning(f"Curl fallback failed for {full_url}: {e}")

    return None


def _parse_espn_competition_score(comp: Dict[str, Any]) -> Tuple[str, int, int, int, bool]:
    """
    Parse linescores into (score_str, total_games, w_sets, l_sets, deciding_set).
    ``score_str`` is written from the WINNER's perspective, e.g. ('6-4 3-6 7-6(4)', 32, 2, 1, True).
    """
    comps = comp.get("competitors", [])
    if len(comps) != 2:
        return ("", 0, 0, 0, False)

    winner_idx = 0 if comps[0].get("winner", False) else 1
    ls_w = comps[winner_idx].get("linescores", [])
    ls_l = comps[1 - winner_idx].get("linescores", [])

    score_parts = []
    total_games = 0
    w_sets = 0
    l_sets = 0

    for sw, sl in zip(ls_w, ls_l):
        vw = int(sw.get("value", 0))
        vl = int(sl.get("value", 0))
        total_games += (vw + vl)

        if sw.get("winner", False) or vw > vl:
            w_sets += 1
        elif sl.get("winner", False) or vl > vw:
            l_sets += 1

        tbw = sw.get("tiebreak")
        tbl = sl.get("tiebreak")
        if tbw is not None and tbl is not None:
            score_parts.append(f"{vw}-{vl}({min(tbw, tbl)})")
        else:
            score_parts.append(f"{vw}-{vl}")

    score_str = " ".join(score_parts)
    is_best_of_5 = len(ls_w) > 3 or (w_sets == 3 and l_sets == 2)
    deciding_set = (w_sets == 3 and l_sets == 2) if is_best_of_5 else (w_sets == 2 and l_sets == 1)

    return (score_str, total_games, w_sets, l_sets, deciding_set)


def fetch_espn_upcoming_tennis(circuit: str = "wta", days_ahead: int = 7) -> List[Dict[str, Any]]:
    """Fetch real upcoming scheduled tournament matches from ESPN Tennis API."""
    circuit_code = circuit.lower()
    url = f"{ESPN_TENNIS_BASE_URL}/{circuit_code}/scoreboard"

    now = datetime.now(timezone.utc)
    start_d = now.strftime("%Y%m%d")
    end_d = datetime.fromtimestamp(now.timestamp() + (days_ahead * 86400), timezone.utc).strftime("%Y%m%d")

    data = _espn_tennis_get(url, {"dates": f"{start_d}-{end_d}"})
    if not data:
        return []

    fixtures = []
    events = data.get("events", [])

    for e in events:
        t_name = e.get("name", "Tournament")
        # Determine surface from tournament name or venue
        surface = "Hard"
        if any(w in t_name.lower() for w in ["ljubljana", "valencia", "clay", "terre", "roma", "madrid", "roland"]):
            surface = "Clay"
        elif any(w in t_name.lower() for w in ["wimbledon", "grass", "queen", "halle", "mallorca"]):
            surface = "Grass"

        for g in e.get("groupings", []):
            round_name = g.get("group", {}).get("name") or "Round of 32"
            for comp in g.get("competitions", []):
                if comp.get("status", {}).get("type", {}).get("completed", False):
                    continue

                d_iso = comp.get("date", "")
                d_str = d_iso[:10] if d_iso else now.strftime("%Y-%m-%d")

                competitors = comp.get("competitors", [])
                if len(competitors) != 2:
                    continue

                p1_raw = competitors[0].get("athlete", {}).get("displayName")
                p2_raw = competitors[1].get("athlete", {}).get("displayName")

                if not p1_raw or not p2_raw or p1_raw == "TBD" or p2_raw == "TBD":
                    continue

                p1_norm = normalize_player_name(p1_raw)
                p2_norm = normalize_player_name(p2_raw)

                m_id = f"{circuit.upper()}_{p1_norm}_{p2_norm}_{d_str}".replace(" ", "_")

                fixtures.append({
                    "match_id": m_id,
                    "circuit": circuit.upper(),
                    "tourney_name": t_name,
                    "date": d_str,
                    "round": round_name,
                    "surface": surface,
                    "p1_name": p1_norm,
                    "p2_name": p2_norm,
                    "best_of": 3,
                    "status": "Scheduled",
                    "is_real_schedule": True,
                })

    logger.info(f"Fetched {len(fixtures)} real upcoming {circuit.upper()} matches from ESPN")
    return fixtures


def fetch_espn_recent_completed_matches(circuit: str = "wta", days_back: int = 28) -> List[Dict[str, Any]]:
    """Fetch all completed tournament matches across the past N days from ESPN Tennis."""
    circuit_code = circuit.lower()
    url = f"{ESPN_TENNIS_BASE_URL}/{circuit_code}/scoreboard"

    now = datetime.now(timezone.utc)
    start_d = datetime.fromtimestamp(now.timestamp() - (days_back * 86400), timezone.utc).strftime("%Y%m%d")
    end_d = now.strftime("%Y%m%d")

    data = _espn_tennis_get(url, {"dates": f"{start_d}-{end_d}"})
    if not data:
        return []

    completed = []
    events = data.get("events", [])

    for e in events:
        t_name = e.get("name", "Tournament")
        surface = "Hard"
        if any(w in t_name.lower() for w in ["ljubljana", "valencia", "clay", "terre", "roma", "madrid", "roland"]):
            surface = "Clay"
        elif any(w in t_name.lower() for w in ["wimbledon", "grass", "queen", "halle", "mallorca"]):
            surface = "Grass"

        is_grand_slam = "us open" in t_name.lower() or "wimbledon" in t_name.lower() or "french" in t_name.lower() or "australian" in t_name.lower()
        best_of = 5 if (is_grand_slam and circuit_code == "atp") else 3

        for g in e.get("groupings", []):
            round_name = g.get("group", {}).get("name") or "Main Draw"
            for comp in g.get("competitions", []):
                if not comp.get("status", {}).get("type", {}).get("completed", False):
                    continue

                d_iso = comp.get("date", "")
                d_str = d_iso[:10] if d_iso else now.strftime("%Y-%m-%d")

                competitors = comp.get("competitors", [])
                if len(competitors) != 2:
                    continue

                p1_raw = competitors[0].get("athlete", {}).get("displayName")
                p2_raw = competitors[1].get("athlete", {}).get("displayName")

                if not p1_raw or not p2_raw:
                    continue

                winner_comp = competitors[0] if competitors[0].get("winner") else (competitors[1] if competitors[1].get("winner") else None)
                if not winner_comp:
                    continue

                winner_raw = winner_comp.get("athlete", {}).get("displayName")
                winner_norm = normalize_player_name(winner_raw)
                p1_norm = normalize_player_name(p1_raw)
                p2_norm = normalize_player_name(p2_raw)

                score_str, total_games, w_sets, l_sets, decider = _parse_espn_competition_score(comp)

                completed.append({
                    "circuit": circuit.upper(),
                    "tourney_name": t_name,
                    "surface": surface,
                    "date": d_str,
                    "round": round_name,
                    "p1_name": p1_norm,
                    "p2_name": p2_norm,
                    "winner": winner_norm,
                    "score": score_str or None,
                    "total_games": total_games,
                    "w_sets": w_sets,
                    "l_sets": l_sets,
                    "deciding_set": decider,
                    "best_of": best_of,
                })

    logger.info(f"Fetched {len(completed)} completed {circuit.upper()} matches from ESPN (dates {start_d} to {end_d})")
    return completed


def update_upcoming_tennis_matches() -> List[Dict[str, Any]]:
    """Refresh the persistent upcoming_matches.json with real active tournament fixtures."""
    all_matches = []
    wta_matches = fetch_espn_upcoming_tennis("wta", days_ahead=7)
    atp_matches = fetch_espn_upcoming_tennis("atp", days_ahead=7)
    all_matches.extend(wta_matches)
    all_matches.extend(atp_matches)

    if all_matches:
        out_file = UPCOMING_DATA_DIR / "upcoming_matches.json"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(all_matches, f, indent=2)
        logger.info(f"Saved {len(all_matches)} real upcoming tennis matches to {out_file}")

    return all_matches


def reconcile_tennis_tracker_with_espn(tracker=None, days_back: int = 28) -> Dict[str, Any]:
    """
    Grade PENDING predictions against completed ESPN results through PredictionTracker,
    the only writer of the ledger. A result is used only when the same pair played within
    3 days of the prediction's date; graded records are never touched.
    """
    from tennis_core.betting.tracker import PredictionTracker

    tracker = tracker or PredictionTracker()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    pending = [
        m for m in tracker.predictions
        if m.get("status") == "PENDING" and str(m.get("date") or "")[:10] and str(m.get("date"))[:10] <= today_str
    ]
    if not pending:
        return {"reconciled": 0, "total": len(tracker.predictions)}

    espn_completed = []
    espn_completed.extend(fetch_espn_recent_completed_matches("wta", days_back=days_back))
    espn_completed.extend(fetch_espn_recent_completed_matches("atp", days_back=days_back))
    if not espn_completed:
        logger.info("No completed ESPN matches retrieved for reconciliation.")
        return {"reconciled": 0, "total": len(tracker.predictions)}

    def _match_key(p1: str, p2: str) -> tuple:
        return tuple(sorted([strip_accents(p1).lower().strip(), strip_accents(p2).lower().strip()]))

    completed_map: Dict[tuple, List[Dict[str, Any]]] = {}
    for cm in espn_completed:
        completed_map.setdefault(_match_key(cm["p1_name"], cm["p2_name"]), []).append(cm)

    reconciled_count = 0
    with tracker.batch():
        for m in pending:
            try:
                pred_day = datetime.strptime(str(m["date"])[:10], "%Y-%m-%d")
            except ValueError:
                continue
            candidates = []
            for c in completed_map.get(_match_key(m.get("p1_name", ""), m.get("p2_name", "")), []):
                try:
                    gap = abs((datetime.strptime(c["date"], "%Y-%m-%d") - pred_day).days)
                except (KeyError, ValueError):
                    continue
                if gap <= 3:
                    candidates.append((gap, c))
            if not candidates:
                continue
            matched = min(candidates, key=lambda gc: gc[0])[1]
            graded = tracker.grade_match(
                m["match_id"],
                actual_winner=matched["winner"],
                score=matched["score"] or None,
                total_games=matched.get("total_games") or None,
                w_sets=matched.get("w_sets"),
                l_sets=matched.get("l_sets"),
                deciding_set=matched.get("deciding_set"),
            )
            if graded and graded.get("status") != "PENDING":
                reconciled_count += 1

    logger.info(f"Reconciled {reconciled_count} pending tennis predictions with ESPN results.")
    return {"reconciled": reconciled_count, "total": len(tracker.predictions)}
