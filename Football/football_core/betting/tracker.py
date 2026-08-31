"""Prediction Archive, Result Reconciliation, Model Verification & Accuracy Engine."""
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np

from football_core.config import TRACKER_FILE

logger = logging.getLogger(__name__)


class PredictionTracker:
    """
    Manages logged match predictions and reconciles them against actual results
    for purely statistical model verification (Accuracy, Log Loss, MAE, Calibration)
    as well as optional betting analysis.
    """

    def __init__(self, storage_file: Path = TRACKER_FILE):
        self.storage_file = storage_file
        self.predictions: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        """Load stored predictions from disk."""
        if self.storage_file.exists():
            try:
                with open(self.storage_file, "r", encoding="utf-8") as f:
                    self.predictions = json.load(f)
            except Exception as e:
                logger.error(f"Error loading tracker file {self.storage_file}: {e}")
                self.predictions = []
        else:
            self.predictions = []

    def save(self):
        """Persist predictions to disk."""
        try:
            self.storage_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump(self.predictions, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save predictions to {self.storage_file}: {e}")

    def log_full_match_prediction(self, pred_item: Dict[str, Any]) -> bool:
        """
        Log a complete multi-category match prediction for statistical verification.
        Stores full model expectancies across 1X2, Goals, BTTS, Corners, Cards, and Scoreline.
        """
        meta = pred_item.get("fixture_meta", {})
        match_id = meta.get("match_id") or f"{pred_item.get('league_key')}_{pred_item.get('home_team')}_{pred_item.get('away_team')}_{meta.get('date', 'date')}"
        
        p_home = float(pred_item.get("prob_home", 0.33))
        p_draw = float(pred_item.get("prob_draw", 0.33))
        p_away = float(pred_item.get("prob_away", 0.33))
        
        # Predicted 1X2 outcome based on highest probability
        if p_home >= p_draw and p_home >= p_away:
            pred_1x2 = "Home"
        elif p_away >= p_home and p_away >= p_draw:
            pred_1x2 = "Away"
        else:
            pred_1x2 = "Draw"

        p_o25 = float(pred_item.get("prob_over25", 0.5))
        pred_o25 = "Over 2.5" if p_o25 >= 0.50 else "Under 2.5"

        p_btts = float(pred_item.get("prob_btts_yes", 0.5))
        pred_btts = "Yes" if p_btts >= 0.50 else "No"

        p_corn_o95 = float(pred_item.get("prob_corners_over95", 0.5))
        pred_corn_o95 = "Over 9.5" if p_corn_o95 >= 0.50 else "Under 9.5"

        p_card_o35 = float(pred_item.get("prob_cards_over35", 0.5))
        pred_card_o35 = "Over 3.5" if p_card_o35 >= 0.50 else "Under 3.5"

        ref_info = pred_item.get("referee", {})
        ref_name = ref_info.get("referee_name") if isinstance(ref_info, dict) else str(ref_info)

        record = {
            "match_id": match_id,
            "date": meta.get("date", str(pd.Timestamp.now().date())),
            "league": pred_item.get("league_key"),
            "league_name": meta.get("league_name", pred_item.get("league_key")),
            "home_team": pred_item.get("home_team"),
            "away_team": pred_item.get("away_team"),
            "referee": ref_name,
            
            # 1X2 Projections
            "prob_home": p_home,
            "prob_draw": p_draw,
            "prob_away": p_away,
            "pred_1x2": pred_1x2,

            # Goals Projections
            "exp_goals_home": float(pred_item.get("expected_goals_home", 1.3)),
            "exp_goals_away": float(pred_item.get("expected_goals_away", 1.1)),
            "exp_total_goals": float(pred_item.get("expected_goals_home", 1.3) + pred_item.get("expected_goals_away", 1.1)),
            "prob_over25": p_o25,
            "prob_under25": float(pred_item.get("prob_under25", 1.0 - p_o25)),
            "pred_over25": pred_o25,

            # BTTS Projections
            "prob_btts_yes": p_btts,
            "prob_btts_no": float(pred_item.get("prob_btts_no", 1.0 - p_btts)),
            "pred_btts": pred_btts,

            # Corners Projections
            "exp_corners": float(pred_item.get("expected_corners", 9.5)),
            "prob_corners_over95": p_corn_o95,
            "prob_corners_under95": float(pred_item.get("prob_corners_under95", 1.0 - p_corn_o95)),
            "pred_corners_o95": pred_corn_o95,

            # Cards Projections
            "exp_cards": float(pred_item.get("expected_cards", 4.2)),
            "prob_cards_over35": p_card_o35,
            "prob_cards_under35": float(pred_item.get("prob_cards_under35", 1.0 - p_card_o35)),
            "pred_cards_o35": pred_card_o35,

            # Scoreline
            "pred_score": pred_item.get("most_likely_score", "1-1"),

            # Optional Betting metadata
            "best_pick": pred_item.get("best_pick", {}),
            "market_category": pred_item.get("best_pick", {}).get("market", "1X2"),

            # Settlement Status
            "status": "pending",
            "actual_score": None,
            "actual_winner": None,  # 'Home', 'Draw', 'Away'
            "actual_goals": None,
            "actual_btts": None,
            "actual_corners": None,
            "actual_cards": None,

            # Verification Correctness flags
            "correct_1x2": None,
            "correct_over25": None,
            "correct_btts": None,
            "correct_corners_o95": None,
            "correct_cards_o35": None,
            "correct_score": None,
            "goal_error": None,
            "corner_error": None,
            "card_error": None,
        }

        # Check if already logged
        for idx, existing in enumerate(self.predictions):
            if existing.get("match_id") == match_id:
                if existing.get("status") != "settled":
                    self.predictions[idx] = {**existing, **record}
                    self.save()
                return False

        self.predictions.append(record)
        self.save()
        return True

    def reconcile_with_completed_matches(self, completed_df: pd.DataFrame) -> int:
        """
        Reconcile pending predictions against historical/completed match statistics
        and evaluate pure model prediction accuracy across all dimensions.
        """
        if completed_df.empty:
            return 0

        settled_count = 0
        for pred in self.predictions:
            if pred.get("status") == "settled":
                continue

            h = pred.get("home_team")
            a = pred.get("away_team")
            pred_date_str = pred.get("date")

            # Match team names and ensure match occurred on or near the fixture date (+/- 3 days)
            team_matches = completed_df[
                (completed_df["HomeTeam"] == h) &
                (completed_df["AwayTeam"] == a)
            ]

            if team_matches.empty:
                continue

            if pred_date_str:
                try:
                    pred_dt = pd.to_datetime(pred_date_str).tz_localize(None) if hasattr(pd.to_datetime(pred_date_str), "tz_localize") else pd.to_datetime(pred_date_str)
                    match_row = team_matches[
                        (team_matches["Date"] >= (pred_dt - pd.Timedelta(days=3))) &
                        (team_matches["Date"] <= (pred_dt + pd.Timedelta(days=3)))
                    ]
                except Exception:
                    match_row = team_matches
            else:
                match_row = pd.DataFrame()

            if not match_row.empty:
                row = match_row.iloc[-1]
                fthg = int(row["FTHG"])
                ftag = int(row["FTAG"])
                ftr = str(row["FTR"])  # 'H', 'D', 'A'
                score_str = f"{fthg}-{ftag}"
                total_goals = fthg + ftag
                actual_winner = "Home" if ftr == "H" else ("Away" if ftr == "A" else "Draw")
                actual_btts = bool(fthg > 0 and ftag > 0)

                hc = int(row.get("HC", 0) or 0)
                ac = int(row.get("AC", 0) or 0)
                actual_corners = hc + ac

                hy = int(row.get("HY", 0) or 0)
                ay = int(row.get("AY", 0) or 0)
                hr = int(row.get("HR", 0) or 0)
                ar = int(row.get("AR", 0) or 0)
                actual_cards = hy + ay + hr + ar

                # 1. Evaluate 1X2 Verification
                h_name = str(pred.get("home_team", "Home")).lower()
                a_name = str(pred.get("away_team", "Away")).lower()
                actual_1x2_type = "Home" if fthg > ftag else ("Away" if ftag > fthg else "Draw")
                actual_winner = f"{pred.get('home_team')} Win" if fthg > ftag else (f"{pred.get('away_team')} Win" if ftag > fthg else "Draw")

                pred_1x2 = str(pred.get("pred_1x2", "")).lower().strip()
                if actual_1x2_type == "Home":
                    correct_1x2 = ("home" in pred_1x2 or h_name in pred_1x2 or pred_1x2 in ["1", "h"])
                elif actual_1x2_type == "Away":
                    correct_1x2 = ("away" in pred_1x2 or a_name in pred_1x2 or pred_1x2 in ["2", "a"])
                else:
                    correct_1x2 = ("draw" in pred_1x2 or pred_1x2 in ["x", "d"])

                # 2. Evaluate Over/Under 2.5 Goals
                pred_o25 = pred.get("pred_over25", "Over 2.5")
                actual_o25 = "Over 2.5" if total_goals > 2.5 else "Under 2.5"
                correct_o25 = (pred_o25 == actual_o25)

                # 3. Evaluate BTTS
                pred_btts = pred.get("pred_btts", "Yes")
                actual_btts_str = "Yes" if actual_btts else "No"
                correct_btts = (pred_btts == actual_btts_str)

                # 4. Evaluate Corners Over 9.5
                pred_corn = pred.get("pred_corners_o95", "Over 9.5")
                actual_corn_str = "Over 9.5" if actual_corners > 9.5 else "Under 9.5"
                correct_corn = (pred_corn == actual_corn_str)

                # 5. Evaluate Cards Over 3.5
                pred_cards = pred.get("pred_cards_o35", "Over 3.5")
                actual_cards_str = "Over 3.5" if actual_cards > 3.5 else "Under 3.5"
                correct_cards = (pred_cards == actual_cards_str)

                # 6. Errors
                goal_err = abs(float(pred.get("exp_total_goals", 2.5)) - total_goals)
                corn_err = abs(float(pred.get("exp_corners", 9.5)) - actual_corners)
                card_err = abs(float(pred.get("exp_cards", 4.2)) - actual_cards)
                correct_score = bool(pred.get("pred_score") == score_str)

                # Update Record
                pred["status"] = "settled"
                pred["actual_score"] = score_str
                pred["actual_winner"] = actual_winner
                pred["actual_goals"] = total_goals
                pred["actual_btts"] = actual_btts_str
                pred["actual_corners"] = actual_corners
                pred["actual_cards"] = actual_cards

                pred["correct_1x2"] = bool(correct_1x2)
                pred["correct_over25"] = bool(correct_o25)
                pred["correct_btts"] = bool(correct_btts)
                pred["correct_corners_o95"] = bool(correct_corn)
                pred["correct_cards_o35"] = bool(correct_cards)
                pred["correct_score"] = bool(correct_score)
                pred["goal_error"] = round(float(goal_err), 2)
                pred["corner_error"] = round(float(corn_err), 2)
                pred["card_error"] = round(float(card_err), 2)

                # Betting calculation (optional)
                best_pick = pred.get("best_pick", {})
                market = best_pick.get("market") or pred.get("market_category", "1X2")
                selection = best_pick.get("selection", "")
                odds = float(best_pick.get("odds", 1.0) or 1.0)
                won_bet = False
                if market == "1X2":
                    won_bet = correct_1x2
                elif market in ["Goals", "Totals"]:
                    won_bet = correct_o25
                elif market == "BTTS":
                    won_bet = correct_btts
                elif market == "Corners":
                    won_bet = correct_corn
                elif market == "Cards":
                    won_bet = correct_cards

                pred["won"] = bool(won_bet)
                pred["flat_pnl"] = round(float((100.0 * (odds - 1.0)) if won_bet else -100.0), 2)

                settled_count += 1

        if settled_count > 0:
            self.save()
            logger.info(f"Reconciled and settled {settled_count} predictions for model verification.")

        return settled_count

    def grade_single_match(
        self, 
        match_id: str, 
        fthg: int, 
        ftag: int, 
        hc: int = 5, 
        ac: int = 4, 
        cards: int = 4,
        actual_xg: Optional[float] = None,
        referee: Optional[str] = None
    ) -> bool:
        """Manually settle and grade a specific football match prediction with real scores & stats."""
        pred = next((p for p in self.predictions if p.get("match_id") == match_id), None)
        if not pred:
            return False

        score_str = f"{fthg}-{ftag}"
        total_goals = fthg + ftag
        actual_1x2_type = "Home" if fthg > ftag else ("Away" if ftag > fthg else "Draw")
        actual_winner = f"{pred.get('home_team')} Win" if fthg > ftag else (f"{pred.get('away_team')} Win" if ftag > fthg else "Draw")
        actual_btts = bool(fthg > 0 and ftag > 0)
        actual_corners = hc + ac
        actual_cards = cards

        h_name = str(pred.get("home_team", "Home")).lower()
        a_name = str(pred.get("away_team", "Away")).lower()
        pred_1x2 = str(pred.get("pred_1x2", "")).lower().strip()
        if actual_1x2_type == "Home":
            correct_1x2 = ("home" in pred_1x2 or h_name in pred_1x2 or pred_1x2 in ["1", "h"])
        elif actual_1x2_type == "Away":
            correct_1x2 = ("away" in pred_1x2 or a_name in pred_1x2 or pred_1x2 in ["2", "a"])
        else:
            correct_1x2 = ("draw" in pred_1x2 or pred_1x2 in ["x", "d"])

        pred_o25 = pred.get("pred_over25", "Over 2.5")
        actual_o25 = "Over 2.5" if total_goals > 2.5 else "Under 2.5"
        correct_o25 = (pred_o25 == actual_o25)

        pred_btts = pred.get("pred_btts", "Yes")
        actual_btts_str = "Yes" if actual_btts else "No"
        correct_btts = (pred_btts == actual_btts_str)

        pred_corn = pred.get("pred_corners_o95", "Over 9.5")
        actual_corn_str = "Over 9.5" if actual_corners > 9.5 else "Under 9.5"
        correct_corn = (pred_corn == actual_corn_str)

        pred_cards = pred.get("pred_cards_o35", "Over 3.5")
        actual_cards_str = "Over 3.5" if actual_cards > 3.5 else "Under 3.5"
        correct_cards = (pred_cards == actual_cards_str)

        goal_err = abs(float(pred.get("exp_total_goals", 2.5)) - total_goals)
        corn_err = abs(float(pred.get("exp_corners", 9.5)) - actual_corners)
        card_err = abs(float(pred.get("exp_cards", 4.2)) - actual_cards)
        correct_score = bool(pred.get("pred_score") == score_str)

        pred["status"] = "settled"
        pred["actual_score"] = score_str
        pred["actual_winner"] = actual_winner
        pred["actual_goals"] = total_goals
        pred["actual_btts"] = actual_btts_str
        pred["actual_corners"] = actual_corners
        pred["actual_cards"] = actual_cards
        if actual_xg is not None:
            pred["actual_xg"] = round(float(actual_xg), 2)
        if referee and referee.strip():
            pred["referee"] = referee.strip()

        pred["correct_1x2"] = bool(correct_1x2)
        pred["correct_over25"] = bool(correct_o25)
        pred["correct_btts"] = bool(correct_btts)
        pred["correct_corners_o95"] = bool(correct_corn)
        pred["correct_cards_o35"] = bool(correct_cards)
        pred["correct_score"] = bool(correct_score)
        pred["goal_error"] = round(float(goal_err), 2)
        pred["corner_error"] = round(float(corn_err), 2)
        pred["card_error"] = round(float(card_err), 2)

        best_pick = pred.get("best_pick", {})
        market = best_pick.get("market") or pred.get("market_category", "1X2")
        odds = float(best_pick.get("odds", 1.0) or 1.0)
        won_bet = False
        if market == "1X2":
            won_bet = correct_1x2
        elif market in ["Goals", "Totals"]:
            won_bet = correct_o25
        elif market == "BTTS":
            won_bet = correct_btts
        elif market == "Corners":
            won_bet = correct_corn
        elif market == "Cards":
            won_bet = correct_cards

        pred["won"] = bool(won_bet)
        pred["flat_pnl"] = round(float((100.0 * (odds - 1.0)) if won_bet else -100.0), 2)

        self.save()
        return True
