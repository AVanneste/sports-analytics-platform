"""Export consolidated, fully-modeled sports analytics payload for the modern web frontend."""
import json
import logging
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FOOTBALL_DIR = PROJECT_ROOT / "Football"
TENNIS_DIR = PROJECT_ROOT / "Tennis"

for p in [PROJECT_ROOT, FOOTBALL_DIR, TENNIS_DIR]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import compat
import numpy as np
import pandas as pd

from football_core.models.predictor import FootballPredictor
from football_core.models.explain import get_match_key_drivers
from football_core.config import LEAGUES
from football_core.ai.pre_bet_auditor import audit_football_match
from football_core.betting.diagnostics import run_ledger_diagnostics
from tennis_core.models.predictor import TennisPredictor
from tennis_core.ai.pre_bet_auditor import audit_tennis_match
from tennis_core.data.espn_tennis import reconcile_tennis_tracker_with_espn

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("WebExporter")


def load_json_safe(path: Path, default=None):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Error reading {path}: {e}")
        return default


def enrich_football_upcoming(raw_fixtures: List[Dict], predictor: FootballPredictor) -> tuple[List[Dict], List[Dict]]:
    """Enrich all real upcoming football fixtures with multi-market predictions, tactical drivers, form & H2H."""
    enriched = []
    all_picks_flat = []

    now_utc = datetime.now(timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")
    raw_fixtures = [f for f in raw_fixtures if (f.get("date") or "")[:10] >= today_str]

    for f in raw_fixtures:
        l_k = f.get("league")
        h_team = f.get("home_team")
        a_team = f.get("away_team")
        
        try:
            tourn = f.get("league_name") or LEAGUES.get(l_k, {}).get("name")
            is_neut = bool(f.get("is_neutral") if f.get("is_neutral") is not None else f.get("neutral", False))

            pred = predictor.predict_match(
                league_key=l_k,
                home_team=h_team,
                away_team=a_team,
                referee=f.get("referee"),
                is_neutral=is_neut,
                tournament=tourn,
                odds_home=f.get("odds_home"),
                odds_draw=f.get("odds_draw"),
                odds_away=f.get("odds_away"),
                odds_over25=f.get("odds_over25"),
                odds_under25=f.get("odds_under25"),
                odds_btts_yes=f.get("odds_btts_yes"),
                odds_btts_no=f.get("odds_btts_no"),
                odds_corners_over95=f.get("odds_corners_over95"),
                odds_corners_under95=f.get("odds_corners_under95"),
                odds_cards_over35=f.get("odds_cards_over35"),
                odds_cards_under35=f.get("odds_cards_under35"),
                match_date=f.get("date"),
            )

            # Extract Tactical Drivers
            drivers = get_match_key_drivers(pred)

            # Extract Summary stats & form
            h_stats = predictor.get_team_summary_stats(l_k, h_team)
            a_stats = predictor.get_team_summary_stats(l_k, a_team)
            h_rec = predictor.get_team_recent_matches(l_k, h_team, n=5)
            a_rec = predictor.get_team_recent_matches(l_k, a_team, n=5)
            h2h_rec = predictor.get_h2h_matches(l_k, h_team, a_team, n=5)

            # Flat market selections for top confidence ranking
            market_options = [
                {"market": "1X2", "selection": f"{h_team} Win", "prob": pred["prob_home"], "fair_odds": pred["fair_odds_home"], "odds": f.get("odds_home")},
                {"market": "1X2", "selection": "Draw", "prob": pred["prob_draw"], "fair_odds": pred["fair_odds_draw"], "odds": f.get("odds_draw")},
                {"market": "1X2", "selection": f"{a_team} Win", "prob": pred["prob_away"], "fair_odds": pred["fair_odds_away"], "odds": f.get("odds_away")},
                {"market": "BTTS", "selection": "BTTS Yes", "prob": pred["prob_btts_yes"], "fair_odds": pred["fair_odds_btts_yes"], "odds": f.get("odds_btts_yes")},
                {"market": "BTTS", "selection": "BTTS No", "prob": pred["prob_btts_no"], "fair_odds": pred["fair_odds_btts_no"], "odds": f.get("odds_btts_no")},
            ]

            # Multi-line Goals (evaluate 1.5, 2.5, 3.5, and primary)
            for gl in pred.get("goal_lines", []):
                l_val = gl["line"]
                if l_val in (1.5, 2.5, 3.5) or gl.get("is_primary"):
                    o_odds = f.get("odds_over25") if l_val == 2.5 else None
                    u_odds = f.get("odds_under25") if l_val == 2.5 else None
                    market_options.append({"market": "Goals", "selection": f"Over {l_val} Goals", "prob": gl["prob_over"], "fair_odds": gl["fair_odds_over"], "odds": o_odds})
                    market_options.append({"market": "Goals", "selection": f"Under {l_val} Goals", "prob": gl["prob_under"], "fair_odds": gl["fair_odds_under"], "odds": u_odds})

            # Multi-line Corners (evaluate 8.5, 9.5, 10.5, and primary)
            for cl in pred.get("corner_lines", []):
                l_val = cl["line"]
                if l_val in (8.5, 9.5, 10.5) or cl.get("is_primary"):
                    o_odds = f.get("odds_corners_over95") if l_val == 9.5 else None
                    u_odds = f.get("odds_corners_under95") if l_val == 9.5 else None
                    market_options.append({"market": "Corners", "selection": f"Over {l_val} Corners", "prob": cl["prob_over"], "fair_odds": cl["fair_odds_over"], "odds": o_odds})
                    market_options.append({"market": "Corners", "selection": f"Under {l_val} Corners", "prob": cl["prob_under"], "fair_odds": cl["fair_odds_under"], "odds": u_odds})

            # Multi-line Cards (evaluate 2.5, 3.5, 4.5, and primary)
            for kdl in pred.get("card_lines", []):
                l_val = kdl["line"]
                if l_val in (2.5, 3.5, 4.5) or kdl.get("is_primary"):
                    o_odds = f.get("odds_cards_over35") if l_val == 3.5 else None
                    u_odds = f.get("odds_cards_under35") if l_val == 3.5 else None
                    market_options.append({"market": "Cards", "selection": f"Over {l_val} Cards", "prob": kdl["prob_over"], "fair_odds": kdl["fair_odds_over"], "odds": o_odds})
                    market_options.append({"market": "Cards", "selection": f"Under {l_val} Cards", "prob": kdl["prob_under"], "fair_odds": kdl["fair_odds_under"], "odds": u_odds})

            best_prob_item = max(market_options, key=lambda x: x["prob"])

            for mo in market_options:
                o_val = mo.get("odds")
                ev_val = ((mo["prob"] * o_val) - 1.0) if (o_val and o_val > 1.0) else None
                # Outlier / Inversion Guard:
                # An EV over +35% on major liquid markets is almost always an inverted quote
                # or data anomaly. Cap to realistic maximum edge (+35.0%)
                if ev_val is not None:
                    if ev_val > 0.35:
                        ev_val = 0.35
                    ev_pct = round(ev_val * 100, 1)
                else:
                    ev_pct = None

                all_picks_flat.append({
                    "match": f"{h_team} vs {a_team}",
                    "date": f.get("date", "-"),
                    "league": f.get("flag", "") + " " + f.get("league_name", l_k),
                    "market": mo["market"],
                    "selection": mo["selection"],
                    "prob": round(mo["prob"] * 100, 1),
                    "fair_odds": mo["fair_odds"],
                    "bookmaker_odds": o_val or "-",
                    "ev": ev_pct,
                })

            item = {
                "match_id": f.get("match_id", f"{l_k}_{h_team}_{a_team}_{f.get('date')}"),
                "league": l_k,
                "league_name": f.get("league_name", LEAGUES.get(l_k, {}).get("name", l_k)),
                "flag": f.get("flag", LEAGUES.get(l_k, {}).get("flag", "⚽")),
                "date": f.get("date"),
                "commence_time": f.get("commence_time"),
                "home_team": h_team,
                "away_team": a_team,
                
                # Elo & Expectancies
                "home_elo": round(pred["home_elo"], 0),
                "away_elo": round(pred["away_elo"], 0),
                "expected_goals_home": round(pred["expected_goals_home"], 2),
                "expected_goals_away": round(pred["expected_goals_away"], 2),
                "expected_total_goals": round(pred.get("expected_total_goals", pred["expected_goals_home"] + pred["expected_goals_away"]), 2),
                "most_likely_score": pred["most_likely_score"],
                "most_likely_score_prob": round(pred["most_likely_score_prob"] * 100, 1),

                # Multi-Line Expectancies & Distributions
                "primary_goal_line": pred.get("primary_goal_line", 2.5),
                "primary_corner_line": pred.get("primary_corner_line", 9.5),
                "primary_card_line": pred.get("primary_card_line", 3.5),
                "goal_lines": pred.get("goal_lines", []),
                "corner_lines": pred.get("corner_lines", []),
                "card_lines": pred.get("card_lines", []),

                # 1X2 Probabilities & Odds
                "prob_home": round(pred["prob_home"], 3),
                "prob_draw": round(pred["prob_draw"], 3),
                "prob_away": round(pred["prob_away"], 3),
                "fair_odds_home": pred["fair_odds_home"],
                "fair_odds_draw": pred["fair_odds_draw"],
                "fair_odds_away": pred["fair_odds_away"],
                "odds_home": f.get("odds_home"),
                "odds_draw": f.get("odds_draw"),
                "odds_away": f.get("odds_away"),

                # Goals & BTTS
                "prob_over25": round(pred["prob_over25"], 3),
                "prob_under25": round(pred["prob_under25"], 3),
                "fair_odds_over25": pred["fair_odds_over25"],
                "fair_odds_under25": pred["fair_odds_under25"],
                "odds_over25": f.get("odds_over25"),
                "odds_under25": f.get("odds_under25"),
                "prob_btts_yes": round(pred["prob_btts_yes"], 3),
                "prob_btts_no": round(pred["prob_btts_no"], 3),
                "fair_odds_btts_yes": pred["fair_odds_btts_yes"],
                "fair_odds_btts_no": pred["fair_odds_btts_no"],
                "odds_btts_yes": f.get("odds_btts_yes"),
                "odds_btts_no": f.get("odds_btts_no"),

                # Corners & Cards
                "expected_corners": round(pred["expected_corners"], 1),
                "prob_corners_over95": round(pred["prob_corners_over95"], 3),
                "prob_corners_under95": round(pred["prob_corners_under95"], 3),
                "fair_odds_corners_over95": pred["fair_odds_corners_over95"],
                "fair_odds_corners_under95": pred["fair_odds_corners_under95"],
                "odds_corners_over95": f.get("odds_corners_over95"),
                "expected_cards": round(pred["expected_cards"], 1),
                "prob_cards_over35": round(pred["prob_cards_over35"], 3),
                "prob_cards_under35": round(pred["prob_cards_under35"], 3),
                "fair_odds_cards_over35": pred["fair_odds_cards_over35"],
                "fair_odds_cards_under35": pred["fair_odds_cards_under35"],
                "odds_cards_over35": f.get("odds_cards_over35"),

                # Referee
                "referee": {
                    "name": (
                        pred.get("referee", {}).get("referee_name")
                        if isinstance(pred.get("referee"), dict) and pred.get("referee", {}).get("referee_name")
                        else (
                            f.get("referee", {}).get("name")
                            if isinstance(f.get("referee"), dict)
                            else (str(f.get("referee")) if f.get("referee") else "Unassigned")
                        )
                    ),
                    "strictness_label": (
                        pred.get("referee", {}).get("strictness_label")
                        if isinstance(pred.get("referee"), dict) and pred.get("referee", {}).get("strictness_label")
                        else (
                            f.get("referee", {}).get("strictness_label")
                            if isinstance(f.get("referee"), dict)
                            else "Balanced"
                        )
                    ),
                    "avg_cards": (
                        pred.get("referee", {}).get("avg_cards")
                        if isinstance(pred.get("referee"), dict) and pred.get("referee", {}).get("avg_cards") is not None
                        else (
                            f.get("referee", {}).get("avg_cards", 4.2)
                            if isinstance(f.get("referee"), dict)
                            else 4.2
                        )
                    ),
                },

                # Recommendation
                "best_pick": pred.get("best_pick"),
                "has_value": pred.get("has_value", False),
                "highest_prob_selection": f"{best_prob_item['selection']} ({best_prob_item['prob']*100:.1f}%)",

                # Insights & Deep Matchup
                "drivers": drivers,
                "home_stats": h_stats,
                "away_stats": a_stats,
                "recent_matches_home": h_rec,
                "recent_matches_away": a_rec,
                "h2h_matches": h2h_rec,
            }

            # Run Pre-Bet AI Auditor on value plays
            if item.get("has_value") or (item.get("best_pick") and (item["best_pick"].get("ev") or 0) > 0):
                try:
                    item["ai_audit"] = audit_football_match(item)
                except Exception as e:
                    logger.debug(f"AI audit failed for {h_team} vs {a_team}: {e}")
                    item["ai_audit"] = None
            else:
                item["ai_audit"] = None

            enriched.append(item)
        except Exception as err:
            logger.debug(f"Skipping match {h_team} vs {a_team}: {err}")
            continue

    return enriched, all_picks_flat


def sanitize_tennis_data(val: Any) -> Any:
    """Recursively clean 'N/A' and 'Unranked / N/A' strings and non-finite floats to None."""
    if isinstance(val, dict):
        return {k: sanitize_tennis_data(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [sanitize_tennis_data(v) for v in val]
    elif isinstance(val, str) and val in ("N/A", "Unranked / N/A"):
        return None
    elif isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None
    return val


def enrich_tennis_upcoming(raw_fixtures: List[Dict], predictor: TennisPredictor) -> tuple[List[Dict], List[Dict]]:
    """Enrich all real upcoming tennis fixtures with surface Elo, Sackmann serve/return, sets & games analytics."""
    enriched = []
    all_picks_flat = []

    now_utc = datetime.now(timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")
    raw_fixtures = [m for m in raw_fixtures if (m.get("date") or "")[:10] >= today_str]

    for m in raw_fixtures:
        circuit = m.get("circuit", "WTA")
        p1 = m.get("p1_name")
        p2 = m.get("p2_name")
        surf = m.get("surface", "Hard")
        fmt = m.get("best_of", 3)
        raw_p1_odds = m.get("p1_odds")
        raw_p2_odds = m.get("p2_odds")

        try:
            pred = predictor.predict_match(
                circuit=circuit,
                p1_name=p1,
                p2_name=p2,
                surface=surf,
                p1_odds=raw_p1_odds,
                p2_odds=raw_p2_odds,
                best_of=fmt,
                bankroll=1000.0,
            )

            # If odds were missing from schedule, leave them as missing and do not estimate
            if not raw_p1_odds or not raw_p2_odds:
                pred["betting"]["p1_odds"] = None
                pred["betting"]["p2_odds"] = None
                pred["betting"]["has_odds"] = False
                pred["betting"]["best_odds"] = None
                pred["betting"]["best_ev"] = None

            betting = pred["betting"]
            ctx = pred["context"]
            sg = pred.get("sets_games", {})
            main_l = sg.get("main_games_line", {})

            # Flat picks
            top_prob = max(pred["p1_prob"], pred["p2_prob"])
            top_p_odds = betting.get("best_odds") or (raw_p1_odds if pred["p1_prob"] >= pred["p2_prob"] else raw_p2_odds)
            ev_val = ((top_prob / 100.0 * top_p_odds) - 1.0) if (top_p_odds and top_p_odds > 1.0) else None
            if ev_val is not None:
                if ev_val > 0.25:
                    ev_val = 0.25
                ev_pct = round(ev_val * 100, 1)
            else:
                ev_pct = None

            all_picks_flat.append({
                "match": f"{p1} vs {p2}",
                "date": m.get("date", "-"),
                "circuit": circuit,
                "market": "Match Winner",
                "selection": f"{pred['predicted_winner']} to Win",
                "prob": top_prob,
                "fair_odds": round(100.0 / max(0.1, top_prob), 2),
                "bookmaker_odds": top_p_odds or "-",
                "ev": ev_pct,
            })

            if sg:
                top_set_p = p1 if sg["p1_win_at_least_1_set_prob"] >= sg["p2_win_at_least_1_set_prob"] else p2
                top_set_val = max(sg["p1_win_at_least_1_set_prob"], sg["p2_win_at_least_1_set_prob"])
                all_picks_flat.append({
                    "match": f"{p1} vs {p2}",
                    "date": m.get("date", "-"),
                    "circuit": circuit,
                    "market": "Set Scoring",
                    "selection": f"{top_set_p} to Win ≥1 Set",
                    "prob": top_set_val,
                    "fair_odds": round(100.0 / max(0.1, top_set_val), 2),
                    "bookmaker_odds": "-",
                    "ev": None,
                })

                if main_l:
                    pick_over = main_l["prob_over"] >= main_l["prob_under"]
                    pick_g_prob = max(main_l["prob_over"], main_l["prob_under"])
                    pick_g_sel = f"Over {main_l['line']} Games" if pick_over else f"Under {main_l['line']} Games"
                    fair_g_odds = main_l["fair_odds_over"] if pick_over else main_l["fair_odds_under"]
                    all_picks_flat.append({
                        "match": f"{p1} vs {p2}",
                        "date": m.get("date", "-"),
                        "circuit": circuit,
                        "market": "Total Games",
                        "selection": pick_g_sel,
                        "prob": pick_g_prob,
                        "fair_odds": fair_g_odds,
                        "bookmaker_odds": "-",
                        "ev": None,
                    })

            item = {
                "match_id": m.get("match_id", f"{circuit}_{p1}_{p2}_{m.get('date')}"),
                "circuit": circuit,
                "tourney_name": m.get("tourney_name", "Tournament"),
                "date": m.get("date"),
                "round": m.get("round", "Main Draw"),
                "surface": surf,
                "best_of": fmt,
                "p1_name": p1,
                "p2_name": p2,

                # Model Prediction
                "p1_prob": pred["p1_prob"],
                "p2_prob": pred["p2_prob"],
                "predicted_winner": pred["predicted_winner"],
                "confidence": pred["confidence"],

                # Betting & Odds
                "betting": betting,
                "has_odds": betting.get("has_odds", False),
                "has_value": betting.get("has_value", False),
                "best_ev": betting.get("best_ev", 0.0),

                # Context & Player Stats
                "context": ctx,

                # Sets & Games Analytics
                "sets_games": sg,
            }

            # Run Pre-Bet AI Auditor on value tennis plays or confidence >= 50%
            if item.get("has_value") or (item.get("best_ev") or 0) > 0 or float(item.get("confidence") or 0) >= 50.0:
                try:
                    item["ai_audit"] = audit_tennis_match(item)
                except Exception as e:
                    logger.debug(f"Tennis AI audit failed for {p1} vs {p2}: {e}")
                    item["ai_audit"] = None
            else:
                item["ai_audit"] = None

            enriched.append(sanitize_tennis_data(item))
        except Exception as err:
            logger.debug(f"Skipping tennis match {p1} vs {p2}: {err}")
            continue

    return enriched, all_picks_flat


def compute_football_tracker_metrics(tracker_list: List[Dict]) -> Dict[str, Any]:
    """Compute verification hit rates and error metrics across settled predictions."""
    settled = [p for p in tracker_list if p.get("status") == "settled"]
    total = len(settled)
    if total == 0:
        return {
            "total_settled": 0, "acc_1x2": 0.0, "acc_o25": 0.0, "acc_btts": 0.0,
            "acc_corners": 0.0, "acc_cards": 0.0, "exact_score_hits": 0, "avg_goal_error": 0.0
        }

    c_1x2 = sum(1 for p in settled if p.get("correct_1x2") is True)
    c_o25 = sum(1 for p in settled if p.get("correct_over25") is True)
    c_btts = sum(1 for p in settled if p.get("correct_btts") is True)

    corn_settled = [p for p in settled if p.get("actual_corners") is not None and float(p.get("actual_corners", -1)) >= 0]
    cards_settled = [p for p in settled if p.get("actual_cards") is not None and float(p.get("actual_cards", -1)) >= 0]

    c_corn = sum(1 for p in corn_settled if p.get("correct_corners_o95") is True)
    c_cards = sum(1 for p in cards_settled if p.get("correct_cards_o35") is True)
    c_score = sum(1 for p in settled if p.get("correct_score") is True)
    
    goal_errs = [float(p.get("goal_error", 0.0)) for p in settled if p.get("goal_error") is not None]
    corn_errs = [float(p.get("corner_error", 0.0)) for p in corn_settled if p.get("corner_error") is not None]
    card_errs = [float(p.get("card_error", 0.0)) for p in cards_settled if p.get("card_error") is not None]

    return {
        "total_settled": total,
        "acc_1x2": round((c_1x2 / total) * 100.0, 1),
        "acc_o25": round((c_o25 / total) * 100.0, 1),
        "acc_btts": round((c_btts / total) * 100.0, 1),
        "acc_corners": round((c_corn / len(corn_settled)) * 100.0, 1) if corn_settled else 0.0,
        "acc_cards": round((c_cards / len(cards_settled)) * 100.0, 1) if cards_settled else 0.0,
        "corners_evaluated_count": len(corn_settled),
        "cards_evaluated_count": len(cards_settled),
        "exact_score_hits": c_score,
        "avg_goal_error": round(float(np.mean(goal_errs)), 2) if goal_errs else 0.0,
        "avg_corner_error": round(float(np.mean(corn_errs)), 2) if corn_errs else 0.0,
        "avg_card_error": round(float(np.mean(card_errs)), 2) if card_errs else 0.0,
    }


def build_web_payload() -> Dict[str, Any]:
    """Generate consolidated, rich JSON payload for the modern web frontend."""
    logger.info("Initializing engines and building consolidated web payload...")

    fb_predictor = FootballPredictor()
    tn_predictor = TennisPredictor()

    # 1. Pipeline Run Metadata
    meta_path = PROJECT_ROOT / "cache" / "pipeline_run_meta.json"
    meta = load_json_safe(meta_path, {})

    # 2. Football Data (Auto-reconcile pending matches and backfill stats via ESPN before export)
    try:
        from football_core.betting.tracker import PredictionTracker
        from football_core.data.espn_client import reconcile_tracker_with_espn, backfill_missing_corners_cards
        fb_tracker_obj = PredictionTracker()
        reconciled_now = reconcile_tracker_with_espn(fb_tracker_obj)
        backfilled_now = backfill_missing_corners_cards(fb_tracker_obj)
        fb_tracker = fb_tracker_obj.predictions
        if reconciled_now > 0 or backfilled_now > 0:
            meta["last_run_timestamp"] = datetime.now().isoformat()
            meta["status"] = "SUCCESS"
            try:
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"Auto-reconciliation skip: {e}")
        fb_tracker_path = PROJECT_ROOT / "Football" / "data" / "cache" / "predictions_tracker.json"
        fb_raw_tracker = load_json_safe(fb_tracker_path, [])
        fb_tracker = fb_raw_tracker if isinstance(fb_raw_tracker, list) else fb_raw_tracker.get("predictions", [])

    now_utc = datetime.now(timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")

    fb_upcoming_path = PROJECT_ROOT / "Football" / "data" / "cache" / "live_upcoming_fixtures.json"
    fb_upcoming_raw = load_json_safe(fb_upcoming_path, {})
    fb_raw_matches = fb_upcoming_raw.get("matches", []) if isinstance(fb_upcoming_raw, dict) else (fb_upcoming_raw or [])
    fb_raw_matches = [m for m in fb_raw_matches if (m.get("date") or "")[:10] >= today_str]

    logger.info(f"Enriching {len(fb_raw_matches)} raw football upcoming fixtures...")
    fb_upcoming, fb_picks_flat = enrich_football_upcoming(fb_raw_matches, fb_predictor)
    logger.info(f"Generated {len(fb_upcoming)} fully modeled football matches ({len(fb_picks_flat)} market picks)")

    fb_metrics = compute_football_tracker_metrics(fb_tracker)
    fb_settled = [m for m in fb_tracker if m.get("status") == "settled"]
    fb_pending = [m for m in fb_tracker if m.get("status") in ("pending", "Pending")]
    fb_future = [m for m in fb_tracker if m.get("is_future")]
    fb_wins = sum(1 for m in fb_settled if m.get("won"))
    fb_flat_pnl = sum(float(m.get("flat_pnl", 0.0)) for m in fb_settled)
    fb_kelly_pnl = sum(float(m.get("kelly_pnl", 0.0)) for m in fb_settled)
    fb_win_rate = round((fb_wins / len(fb_settled) * 100), 1) if fb_settled else 0.0
    fb_total_staked = sum(float(m.get("stake", 100.0)) for m in fb_settled)
    fb_roi_pct = round((fb_flat_pnl / fb_total_staked * 100.0), 1) if fb_total_staked > 0 else 0.0

    # +EV Value Bets Cohort (Strict model recommendations with Positive Expected Value)
    fb_val_settled = [m for m in fb_settled if m.get("has_value")]
    fb_val_wins = sum(1 for m in fb_val_settled if m.get("won"))
    fb_val_flat_pnl = sum(float(m.get("flat_pnl", 0.0)) for m in fb_val_settled)
    fb_val_total_staked = len(fb_val_settled) * 100.0
    fb_val_roi_pct = round((fb_val_flat_pnl / fb_val_total_staked * 100.0), 1) if fb_val_total_staked > 0 else 0.0
    fb_val_win_rate = round((fb_val_wins / len(fb_val_settled) * 100.0), 1) if fb_val_settled else 0.0
    val_ev_list = [float(m.get("best_pick", {}).get("ev", 0.0) or 0.0) for m in fb_val_settled]
    fb_val_avg_ev = round(float(np.mean(val_ev_list) * 100.0), 1) if val_ev_list else 0.0
    fb_val_expected_pnl = round(float(sum(100.0 * ev for ev in val_ev_list)), 2)
    val_odds_list = [float(m.get("best_pick", {}).get("odds", 0.0) or 0.0) for m in fb_val_settled]
    fb_val_avg_odds = round(float(np.mean(val_odds_list)), 2) if val_odds_list else 0.0

    # 3. Tennis Data
    try:
        reconcile_tennis_tracker_with_espn(days_back=28)
    except Exception as e:
        logger.warning(f"Tennis ESPN auto-reconciliation encountered error: {e}")

    tn_archive_path = PROJECT_ROOT / "Tennis" / "data" / "tracker" / "predictions_archive.json"
    tn_tracker = sanitize_tennis_data(load_json_safe(tn_archive_path, []))

    tn_upcoming_path = PROJECT_ROOT / "Tennis" / "data" / "upcoming" / "upcoming_matches.json"
    tn_raw_matches = load_json_safe(tn_upcoming_path, [])
    tn_raw_matches = [m for m in tn_raw_matches if (m.get("date") or "")[:10] >= today_str]

    logger.info(f"Enriching {len(tn_raw_matches)} raw tennis upcoming fixtures...")
    tn_upcoming, tn_picks_flat = enrich_tennis_upcoming(tn_raw_matches, tn_predictor)
    logger.info(f"Generated {len(tn_upcoming)} fully modeled tennis matches ({len(tn_picks_flat)} market picks)")

    tn_metrics_path = PROJECT_ROOT / "Tennis" / "data" / "processed" / "model_metrics.json"
    tn_metrics = load_json_safe(tn_metrics_path, {})

    tn_settled = [m for m in tn_tracker if m.get("status") in ("WON", "LOST", "SETTLED") or m.get("actual_winner")]
    tn_pending = [m for m in tn_tracker if m.get("status") == "PENDING" and not m.get("actual_winner")]
    
    # Pure model winner accuracy
    c_win = sum(
        1 for m in tn_settled
        if m.get("correct_winner") is True
        or m.get("model_correct") is True
        or (m.get("predicted_winner") and m.get("actual_winner") and m.get("predicted_winner") == m.get("actual_winner"))
    )
    tn_model_acc = round((c_win / len(tn_settled) * 100.0), 1) if tn_settled else 0.0

    # Multi-market accuracy metrics
    sets_graded = [m for m in tn_settled if m.get("correct_sets_at_least_1") is not None]
    acc_sets = round((sum(1 for m in sets_graded if m.get("correct_sets_at_least_1") is True) / len(sets_graded) * 100.0), 1) if sets_graded else 0.0

    games_graded = [m for m in tn_settled if m.get("correct_games_ou") is not None]
    acc_games = round((sum(1 for m in games_graded if m.get("correct_games_ou") is True) / len(games_graded) * 100.0), 1) if games_graded else 0.0
    avg_game_err = round(sum(m.get("game_error", 0) for m in games_graded) / len(games_graded), 1) if games_graded else 0.0

    dec_graded = [m for m in tn_settled if m.get("correct_deciding_set") is not None]
    acc_decider = round((sum(1 for m in dec_graded if m.get("correct_deciding_set") is True) / len(dec_graded) * 100.0), 1) if dec_graded else 0.0

    # Disciplined Value Bets
    tn_val_settled = [m for m in tn_settled if m.get("is_value_bet") or m.get("best_ev") or m.get("status") in ("WON", "LOST")]
    tn_val_wins = sum(1 for m in tn_val_settled if m.get("status") == "WON")
    tn_val_pnl = sum(float(m.get("pnl", 0.0)) for m in tn_val_settled)
    tn_val_staked = sum(float(m.get("best_stake") or m.get("stake") or 20.0) for m in tn_val_settled)
    tn_val_win_rate = round((tn_val_wins / len(tn_val_settled) * 100.0), 1) if tn_val_settled else 0.0
    tn_val_roi = round((tn_val_pnl / tn_val_staked * 100.0), 1) if tn_val_staked > 0 else 0.0

    # Diagnostics
    fb_diagnostics = run_ledger_diagnostics(fb_val_settled if fb_val_settled else fb_tracker)
    fb_val_diagnostics = fb_diagnostics
    tn_diagnostics = run_ledger_diagnostics(tn_val_settled if tn_val_settled else tn_settled)

    # Balanced Football Top Picks across all markets (Goals, Corners, Cards, 1X2, BTTS)
    top_picks_balanced = []
    for mkt in ["Goals", "Corners", "Cards", "1X2", "BTTS"]:
        m_items = sorted([p for p in fb_picks_flat if p["market"] == mkt], key=lambda x: x["prob"], reverse=True)[:15]
        top_picks_balanced.extend(m_items)
    top_picks_balanced.extend(sorted(fb_picks_flat, key=lambda x: x["prob"], reverse=True)[:25])

    seen_picks = set()
    fb_top_picks_deduped = []
    for p in top_picks_balanced:
        k = (p["match"], p["market"], p["selection"])
        if k not in seen_picks:
            seen_picks.add(k)
            fb_top_picks_deduped.append(p)

    # 4. Consolidated Payload
    payload = {
        "timestamp": datetime.now().isoformat(),
        "generated_at_unix": time.time(),
        "summary": {
            "overall_status": meta.get("status", "HEALTHY"),
            "last_pipeline_run": meta.get("last_run_timestamp"),
            "football": {
                "settled_count": len(fb_settled),
                "pending_count": len(fb_pending),
                "future_count": len(fb_future),
                "upcoming_count": len(fb_upcoming),
                "value_bets_count": sum(1 for m in fb_upcoming if m.get("has_value")),
                "win_rate_pct": fb_win_rate,
                "flat_pnl": round(fb_flat_pnl, 2),
                "kelly_pnl": round(fb_kelly_pnl, 2),
                "total_staked": round(fb_total_staked, 2),
                "roi_pct": fb_roi_pct,
                "value_bets": {
                    "settled_count": len(fb_val_settled),
                    "wins": fb_val_wins,
                    "losses": len(fb_val_settled) - fb_val_wins,
                    "win_rate_pct": fb_val_win_rate,
                    "flat_pnl": round(fb_val_flat_pnl, 2),
                    "total_staked": round(fb_val_total_staked, 2),
                    "roi_pct": fb_val_roi_pct,
                    "avg_odds": fb_val_avg_odds,
                    "avg_ev_pct": fb_val_avg_ev,
                    "expected_pnl": fb_val_expected_pnl,
                },
                "metrics": fb_metrics,
            },
            "tennis": {
                "settled_count": len(tn_settled),
                "pending_count": len(tn_pending),
                "upcoming_count": len(tn_upcoming),
                "value_bets_count": sum(1 for m in tn_upcoming if m.get("has_value")),
                "win_rate_pct": tn_model_acc,
                "total_pnl": round(tn_val_pnl, 2),
                "total_staked": round(tn_val_staked, 2),
                "roi_pct": tn_val_roi,
                "atp_accuracy": tn_metrics.get("atp", {}).get("accuracy") or 0.0,
                "atp_auc": tn_metrics.get("atp", {}).get("roc_auc") or 0.0,
                "wta_accuracy": tn_metrics.get("wta", {}).get("accuracy") or 0.0,
                "wta_auc": tn_metrics.get("wta", {}).get("roc_auc") or 0.0,
                "metrics": {
                    "acc_winner": tn_model_acc,
                    "acc_sets_line": acc_sets,
                    "acc_games_ou": acc_games,
                    "acc_decider": acc_decider,
                    "avg_game_error": avg_game_err,
                    "total_graded": len(tn_settled),
                },
                "value_bets": {
                    "settled_count": len(tn_val_settled),
                    "wins": tn_val_wins,
                    "losses": len(tn_val_settled) - tn_val_wins,
                    "win_rate_pct": tn_val_win_rate,
                    "total_pnl": round(tn_val_pnl, 2),
                    "total_staked": round(tn_val_staked, 2),
                    "roi_pct": tn_val_roi,
                }
            }
        },
        "football": {
            "upcoming": fb_upcoming,
            "top_picks": fb_top_picks_deduped,
            "tracker": fb_tracker,
            "metrics": fb_metrics,
            "diagnostics": fb_diagnostics,
            "value_diagnostics": fb_val_diagnostics,
        },
        "tennis": {
            "upcoming": tn_upcoming,
            "top_picks": sorted(tn_picks_flat, key=lambda x: x["prob"], reverse=True)[:30],
            "tracker": tn_tracker,
            "metrics": tn_metrics,
            "diagnostics": tn_diagnostics,
        }
    }

    # Save destinations
    out_paths = [
        PROJECT_ROOT / "cache" / "sports_web_data.json",
        PROJECT_ROOT / "web" / "public" / "data" / "sports_data.json",
    ]

    for p in out_paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        logger.info(f"Saved {p.name} ({p.stat().st_size / 1024:.1f} KB)")

    return payload


if __name__ == "__main__":
    build_web_payload()
