"""Batch normalize Football predictions tracker cache."""
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FOOTBALL_DIR = PROJECT_ROOT / "Football"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(FOOTBALL_DIR))

import compat
from football_core.betting.tracker import evaluate_best_pick_win

def normalize_tracker():
    tracker_path = FOOTBALL_DIR / "data" / "cache" / "predictions_tracker.json"
    if not tracker_path.exists():
        print(f"Tracker file not found at {tracker_path}")
        return

    with open(tracker_path, "r", encoding="utf-8") as f:
        predictions = json.load(f)

    print(f"Loaded {len(predictions)} predictions to normalize.")

    draw_count = 0
    unreported_corners_count = 0
    val_bets_count = 0
    total_val_pnl = 0.0

    for d in predictions:
        home_team = d.get("home_team", "Home")
        away_team = d.get("away_team", "Away")
        p_h = float(d.get("prob_home") or 0.33)
        p_d = float(d.get("prob_draw") or 0.33)
        p_a = float(d.get("prob_away") or 0.33)
        mls = str(d.get("most_likely_score") or "")

        # 1. Intelligent Draw prediction & consistent team naming
        is_draw = (p_d >= p_h and p_d >= p_a) or \
                  (abs(p_h - p_a) <= 0.07 and p_d >= 0.26) or \
                  (mls in ["1-1", "0-0"] and abs(p_h - p_a) <= 0.09)

        if is_draw:
            d["pred_1x2"] = "Draw"
            draw_count += 1
        elif p_h >= p_a:
            d["pred_1x2"] = f"{home_team} Win"
        else:
            d["pred_1x2"] = f"{away_team} Win"

        # 2. Consistent Actual Winner
        score = d.get("actual_score")
        if score and "-" in score:
            try:
                hg, ag = map(int, score.split("-"))
                if hg > ag:
                    d["actual_winner"] = f"{home_team} Win"
                    act_type = "Home"
                elif ag > hg:
                    d["actual_winner"] = f"{away_team} Win"
                    act_type = "Away"
                else:
                    d["actual_winner"] = "Draw"
                    act_type = "Draw"
                d["correct_1x2"] = bool(d["pred_1x2"] == d["actual_winner"])
            except Exception:
                d["actual_winner"] = None
                act_type = "Draw"
                d["correct_1x2"] = None
        else:
            d["actual_winner"] = None
            act_type = "Draw"
            d["correct_1x2"] = None

        # 3. Normalize Goals & xG aliases
        exp_h = d.get("expected_goals_home")
        if exp_h is None:
            exp_h = d.get("exp_goals_home", 1.3)
        exp_a = d.get("expected_goals_away")
        if exp_a is None:
            exp_a = d.get("exp_goals_away", 1.1)
        exp_tot = d.get("exp_total_goals")
        if exp_tot is None:
            exp_tot = round(float(exp_h) + float(exp_a), 2)

        d["expected_goals_home"] = round(float(exp_h), 2)
        d["expected_goals_away"] = round(float(exp_a), 2)
        d["exp_goals_home"] = round(float(exp_h), 2)
        d["exp_goals_away"] = round(float(exp_a), 2)
        d["exp_total_goals"] = round(float(exp_tot), 2)

        # 4. Normalize Corners & Cards aliases
        exp_corn = d.get("exp_corners")
        if exp_corn is None:
            exp_corn = d.get("expected_corners", 9.5)
        d["exp_corners"] = round(float(exp_corn), 1)
        d["expected_corners"] = round(float(exp_corn), 1)

        exp_cards = d.get("exp_cards")
        if exp_cards is None:
            exp_cards = d.get("expected_cards", 4.2)
        d["exp_cards"] = round(float(exp_cards), 1)
        d["expected_cards"] = round(float(exp_cards), 1)

        # 5. Handle unrecorded European corners/cards (remove synthetic zeroes and placeholders)
        raw_corn = d.get("actual_corners")
        raw_cards = d.get("actual_cards")
        league = d.get("league", "")

        is_unrecorded = (
            (raw_corn == 0 and raw_cards == 0) or
            (league in ["UEL", "UCL"] and raw_corn == 9 and raw_cards == 4)
        )

        if is_unrecorded:
            d["actual_corners"] = None
            d["actual_cards"] = None
            d["correct_corners_o95"] = None
            d["correct_cards_o35"] = None
            d["corner_error"] = None
            d["card_error"] = None
            unreported_corners_count += 1
        else:
            if raw_corn is not None and raw_corn >= 0:
                pred_corn = d.get("pred_corners_o95", "Over 9.5")
                d["correct_corners_o95"] = bool(
                    (pred_corn == "Over 9.5" and raw_corn > 9.5) or
                    (pred_corn == "Under 9.5" and raw_corn < 9.5)
                )
                d["corner_error"] = round(abs(d["exp_corners"] - raw_corn), 2)

            if raw_cards is not None and raw_cards >= 0:
                pred_cards = d.get("pred_cards_o35", "Over 3.5")
                d["correct_cards_o35"] = bool(
                    (pred_cards == "Over 3.5" and raw_cards > 3.5) or
                    (pred_cards == "Under 3.5" and raw_cards < 3.5)
                )
                d["card_error"] = round(abs(d["exp_cards"] - raw_cards), 2)

        # 6. Value Betting & Financial PnL
        has_val = bool(d.get("has_value"))
        bp = d.get("best_pick")

        if has_val and isinstance(bp, dict) and (bp.get("ev") or 0) > 0:
            d["has_value"] = True
            odds = float(bp.get("odds", 1.0))
            fthg = int(score.split("-")[0]) if score and "-" in score else 0
            ftag = int(score.split("-")[1]) if score and "-" in score else 0
            tot_goals = fthg + ftag
            btts = bool(fthg > 0 and ftag > 0)
            corn_val = d.get("actual_corners")
            card_val = d.get("actual_cards")

            won = evaluate_best_pick_win(
                best_pick=bp,
                actual_1x2_type=act_type,
                total_goals=tot_goals,
                actual_btts=btts,
                actual_corners=corn_val,
                actual_cards=card_val,
                h_name=home_team,
                a_name=away_team
            )
            d["won"] = bool(won)
            pnl = round(100.0 * (odds - 1.0) if won else -100.0, 2)
            d["flat_pnl"] = pnl
            d["stake"] = 100.0
            val_bets_count += 1
            total_val_pnl += pnl
        else:
            d["has_value"] = False
            d["best_pick"] = None
            d["won"] = None
            d["flat_pnl"] = 0.0
            d["kelly_pnl"] = 0.0
            d["stake"] = 0.0

    # Save normalized data
    with open(tracker_path, "w", encoding="utf-8") as f:
        json.dump(predictions, f, indent=2)

    print(f"Successfully normalized {len(predictions)} predictions:")
    print(f" - Draws predicted: {draw_count}")
    print(f" - Unreported corners/cards fixtures: {unreported_corners_count}")
    print(f" - Real +EV Value Bets: {val_bets_count}")
    print(f" - Total Value Bets PnL: {total_val_pnl:+.2f}€")

if __name__ == "__main__":
    normalize_tracker()

