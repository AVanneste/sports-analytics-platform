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

from tennis_core.config import UPCOMING_DATA_DIR, PREDICTIONS_ARCHIVE_PATH
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
    Example output: ('6-4 3-6 7-6(4)', 32, 2, 1, True)
    """
    comps = comp.get("competitors", [])
    if len(comps) != 2:
        return ("", 0, 0, 0, False)

    p1_is_winner = comps[0].get("winner", False)
    ls1 = comps[0].get("linescores", [])
    ls2 = comps[1].get("linescores", [])

    score_parts = []
    total_games = 0
    p1_sets = 0
    p2_sets = 0

    for s1, s2 in zip(ls1, ls2):
        v1 = int(s1.get("value", 0))
        v2 = int(s2.get("value", 0))
        total_games += (v1 + v2)

        if s1.get("winner", False) or v1 > v2:
            p1_sets += 1
        elif s2.get("winner", False) or v2 > v1:
            p2_sets += 1

        tb1 = s1.get("tiebreak")
        tb2 = s2.get("tiebreak")
        if tb1 is not None and tb2 is not None:
            loser_tb = min(tb1, tb2)
            score_parts.append(f"{v1}-{v2}({loser_tb})")
        else:
            score_parts.append(f"{v1}-{v2}")

    score_str = " ".join(score_parts)
    w_sets = p1_sets if p1_is_winner else p2_sets
    l_sets = p2_sets if p1_is_winner else p1_sets

    is_best_of_5 = len(ls1) > 3 or (w_sets == 3 and l_sets == 2)
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
                    "score": score_str or comp.get("status", {}).get("type", {}).get("description", "Final"),
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


def reconcile_tennis_tracker_with_espn(
    tracker_path: Optional[Path] = None,
    predictor: Optional[Any] = None,
    days_back: int = 28
) -> Dict[str, Any]:
    """
    Reconcile pending and historical predictions in predictions_archive.json against completed ESPN outcomes.
    Enriches each settled match with multi-market validation (Winner, Sets >=1, Games O/U line, Deciding Set, Game Error).
    Applies disciplined value bounding to betting PnL.
    """
    path = tracker_path or PREDICTIONS_ARCHIVE_PATH
    if not path.exists():
        return {"reconciled": 0, "total": 0}

    with open(path, "r", encoding="utf-8") as f:
        tracker = json.load(f)

    # Fetch recent completed matches from ESPN
    espn_completed = []
    espn_completed.extend(fetch_espn_recent_completed_matches("wta", days_back=days_back))
    espn_completed.extend(fetch_espn_recent_completed_matches("atp", days_back=days_back))

    if not espn_completed:
        logger.info("No completed ESPN matches retrieved for reconciliation.")
        return {"reconciled": 0, "total": len(tracker)}

    reconciled_count = 0

    # Index completed matches by pair and date
    def _match_key(p1: str, p2: str) -> tuple:
        p1_c = strip_accents(p1).lower().strip()
        p2_c = strip_accents(p2).lower().strip()
        return tuple(sorted([p1_c, p2_c]))

    completed_map = {}
    for cm in espn_completed:
        key = _match_key(cm["p1_name"], cm["p2_name"])
        if key not in completed_map:
            completed_map[key] = []
        completed_map[key].append(cm)

    # Grade or update tracker entries
    for m in tracker:
        p1 = m.get("p1_name", "")
        p2 = m.get("p2_name", "")
        m_date = m.get("date", "")
        key = _match_key(p1, p2)

        candidates = completed_map.get(key, [])
        matched = None
        if candidates:
            if len(candidates) == 1:
                matched = candidates[0]
            else:
                # Pick closest date
                for c in candidates:
                    if abs((datetime.strptime(c["date"], "%Y-%m-%d") - datetime.strptime(m_date[:10], "%Y-%m-%d")).days) <= 4:
                        matched = c
                        break
                if not matched:
                    matched = candidates[-1]

        if matched:
            winner = matched["winner"]
            score = matched["score"]
            actual_games = matched["total_games"]
            decider = matched["deciding_set"]
            w_sets = matched["w_sets"]
            l_sets = matched["l_sets"]

            p1_won = bool(winner and (strip_accents(p1).lower() in strip_accents(winner).lower() or strip_accents(winner).lower() in strip_accents(p1).lower()))
            winner_resolved = p1 if p1_won else p2

            p1_p = float(m.get("p1_prob", 50.0))
            p2_p = float(m.get("p2_prob", 50.0))
            predicted_winner = p1 if p1_p >= p2_p else p2
            fav_prob = max(p1_p, p2_p)

            # Multi-Market Grading
            correct_winner = (winner_resolved == predicted_winner)

            # Sets Market: Favored player wins >= 1 set
            fav_sets = w_sets if (winner_resolved == predicted_winner) else l_sets
            correct_sets_line = (fav_sets >= 1) if (w_sets + l_sets > 0) else None

            # Total Games Line
            sg = m.get("sets_games") or {}
            exp_g = float(sg.get("expected_total_games") or 22.5)
            main_line_info = sg.get("main_games_line") or {}
            main_line = float(main_line_info.get("line") or 22.5)
            model_pred_over = bool(exp_g >= main_line)

            if actual_games > 0:
                actual_is_over = bool(actual_games > main_line)
                correct_games_ou = (actual_is_over == model_pred_over)
                game_error = round(abs(exp_g - actual_games), 1)
            else:
                correct_games_ou = None
                game_error = None

            # Deciding Set
            p_dec = float(sg.get("prob_deciding_set") or 45.0)
            model_pred_decider = (p_dec >= 50.0)
            correct_decider = (decider == model_pred_decider) if (w_sets + l_sets > 0) else None

            # Update match record
            m["actual_winner"] = winner_resolved
            m["score"] = score
            m["actual_games"] = actual_games if actual_games > 0 else None
            m["game_error"] = game_error
            m["correct_winner"] = correct_winner
            m["correct_sets_at_least_1"] = correct_sets_line
            m["correct_games_ou"] = correct_games_ou
            m["correct_deciding_set"] = correct_decider
            m["games_line"] = main_line
            m["exp_total_games"] = exp_g

            # Disciplined Betting Grading
            rec_pick = m.get("recommended_pick") or predicted_winner
            odds = float(m.get("best_odds") or m.get("p1_odds" if rec_pick == p1 else "p2_odds") or 0.0)
            pick_p = p1_p if rec_pick == p1 else p2_p
            edge = float(m.get("best_edge") or ((pick_p / 100.0 * odds) - 1.0) if odds > 1.0 else 0.0)

            # Disciplined criteria: 1.30 <= odds <= 3.20, pick_p >= 32%, edge >= 0.02
            is_disciplined_bet = (1.30 <= odds <= 3.20 and pick_p >= 32.0 and edge >= 0.02)

            if is_disciplined_bet:
                # Quarter-Kelly bankroll sizing
                b = odds - 1.0
                p = pick_p / 100.0
                q = 1.0 - p
                kelly_pct = max(0.01, min(0.05, ((b * p - q) / b) * 0.25))
                stake = round(1000.0 * kelly_pct, 2)

                pick_won = (winner_resolved == rec_pick)
                if pick_won:
                    m["status"] = "WON"
                    m["pnl"] = round(stake * b, 2)
                    m["flat_pnl"] = round(20.0 * b, 2)
                else:
                    m["status"] = "LOST"
                    m["pnl"] = round(-stake, 2)
                    m["flat_pnl"] = -20.0
                m["stake"] = stake
                m["is_value_bet"] = True
            else:
                m["status"] = "NO_BET"
                m["pnl"] = 0.0
                m["flat_pnl"] = 0.0
                m["stake"] = 0.0
                m["is_value_bet"] = False

            reconciled_count += 1

    # Save reconciled tracker
    with open(path, "w", encoding="utf-8") as f:
        json.dump(tracker, f, indent=2, default=str)

    logger.info(f"Successfully reconciled {reconciled_count}/{len(tracker)} tennis predictions with ESPN results.")
    return {"reconciled": reconciled_count, "total": len(tracker)}
