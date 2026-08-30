"""Post-match result tracker, reconciliation engine, pure ML accuracy validator, and PnL/ROI monitor."""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

from tennis_core.config import PREDICTIONS_ARCHIVE_PATH, GRADED_RESULTS_PATH, PNL_HISTORY_PATH
from tennis_core.utils.helpers import match_player_to_database, strip_accents

logger = logging.getLogger(__name__)


class PredictionTracker:
    """Manages the lifecycle of predictions: creation, storage, outcome reconciliation, ML accuracy validation, and PnL tracking."""

    def __init__(self):
        self.archive_path = PREDICTIONS_ARCHIVE_PATH
        self.predictions: List[Dict] = self._load_predictions()

    def _load_predictions(self) -> List[Dict]:
        if self.archive_path.exists():
            try:
                with open(self.archive_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read predictions archive: {e}")
                return []
        return []

    def _save_predictions(self):
        self.archive_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.archive_path, "w", encoding="utf-8") as f:
            json.dump(self.predictions, f, indent=2, default=str)

    def log_prediction(self, pred_dict: Dict) -> str:
        """
        Record a new match prediction into archive. Prevents duplicate entries.
        """
        match_id = pred_dict.get("match_id", f"{pred_dict.get('circuit')}_{pred_dict.get('p1_name')}_{pred_dict.get('p2_name')}_{pred_dict.get('date')}")
        pred_date = pred_dict.get("date")
        p1 = pred_dict.get("p1_name")
        p2 = pred_dict.get("p2_name")
        
        # Check existing by match_id OR matchup pair on date
        existing = next(
            (p for p in self.predictions if p.get("match_id") == match_id or (
                pred_date and p.get("date") == pred_date and (
                    (p.get("p1_name") == p1 and p.get("p2_name") == p2) or
                    (p.get("p1_name") == p2 and p.get("p2_name") == p1)
                )
            )),
            None
        )
        
        if existing:
            existing.update(pred_dict)
            existing["match_id"] = match_id
        else:
            record = {
                "match_id": match_id,
                "created_at": pd.Timestamp.now().isoformat(),
                "status": "PENDING",  # PENDING, WON, LOST, VOID, NO_BET
                "actual_winner": None,
                "score": None,
                "pnl": 0.0,
                "flat_pnl": 0.0,
                **pred_dict
            }
            self.predictions.append(record)
            
        self._save_predictions()
        return match_id

    def grade_match(self, match_id: str, actual_winner: str, score: Optional[str] = None) -> Optional[Dict]:
        """
        Grade a completed match outcome: evaluate pure ML correctness and betting PnL.
        """
        match = next((p for p in self.predictions if p.get("match_id") == match_id), None)
        if not match:
            logger.warning(f"Match {match_id} not found in prediction archive.")
            return None

        p1_name = match["p1_name"]
        p2_name = match["p2_name"]

        # Check if withdrawal / void
        if "void" in actual_winner.lower() or "withdrew" in actual_winner.lower():
            match["actual_winner"] = "Void (Withdrawal)"
            match["score"] = score or "Walkover"
            match["status"] = "VOID"
            match["model_correct"] = None
            match["pnl"] = 0.0
            match["flat_pnl"] = 0.0
            self._save_predictions()
            return match

        # Resolve winner to exact p1_name or p2_name
        winner_resolved = p1_name if strip_accents(actual_winner).lower() in strip_accents(p1_name).lower() or strip_accents(p1_name).lower() in strip_accents(actual_winner).lower() else p2_name

        match["actual_winner"] = winner_resolved
        match["score"] = score
        
        # Pure ML Model Favorite (>50% model probability)
        predicted_fav = p1_name if float(match["p1_prob"]) >= float(match["p2_prob"]) else p2_name
        match["predicted_fav"] = predicted_fav
        match["fav_prob"] = max(float(match["p1_prob"]), float(match["p2_prob"]))
        match["model_correct"] = (winner_resolved == predicted_fav)
        
        # Betting PnL evaluation (Odds & Value Bets)
        rec_pick = match.get("recommended_pick")
        stake = float(match.get("best_stake", 0.0) or 0.0)
        flat_stake = 20.0
        
        if rec_pick and stake > 0:
            odds = float(match.get("best_odds", 1.0) or 1.0)
            pick_won = (strip_accents(rec_pick).lower() in strip_accents(winner_resolved).lower()) or (strip_accents(winner_resolved).lower() in strip_accents(rec_pick).lower())
            
            if pick_won:
                match["status"] = "WON"
                match["pnl"] = round(stake * (odds - 1.0), 2)
                match["flat_pnl"] = round(flat_stake * (odds - 1.0), 2)
            else:
                match["status"] = "LOST"
                match["pnl"] = round(-stake, 2)
                match["flat_pnl"] = round(-flat_stake, 2)
        else:
            match["status"] = "NO_BET"
            match["pnl"] = 0.0
            match["flat_pnl"] = 0.0
            
        self._save_predictions()
        return match

    def auto_reconcile(self, completed_matches_df: pd.DataFrame) -> int:
        """
        Automatically reconcile pending predictions against a dataframe of completed matches.
        Strictly enforces match date window (+- 3 days) to prevent matching future fixtures against historical encounters.
        """
        if completed_matches_df.empty:
            return 0
            
        known_players = list(set(completed_matches_df["winner_name"]).union(set(completed_matches_df["loser_name"])))
        reconciled_count = 0
        
        # Ensure date column is datetime
        df_matches = completed_matches_df.copy()
        if "tourney_date" in df_matches.columns:
            df_matches["match_dt"] = pd.to_datetime(df_matches["tourney_date"].astype(str), errors="coerce")
        elif "date" in df_matches.columns:
            df_matches["match_dt"] = pd.to_datetime(df_matches["date"].astype(str), errors="coerce")
        else:
            df_matches["match_dt"] = pd.NaT

        for pred in self.predictions:
            if pred.get("status") != "PENDING":
                continue
                
            p1_raw = pred["p1_name"]
            p2_raw = pred["p2_name"]
            pred_date_str = pred.get("date")
            
            p1_canon = match_player_to_database(p1_raw, known_players)
            p2_canon = match_player_to_database(p2_raw, known_players)
            
            matches = df_matches[
                ((df_matches["winner_name"] == p1_canon) & (df_matches["loser_name"] == p2_canon)) |
                ((df_matches["winner_name"] == p2_canon) & (df_matches["loser_name"] == p1_canon))
            ]
            
            # Enforce date filtering if prediction has a date
            if pred_date_str and not matches.empty:
                try:
                    p_dt = pd.to_datetime(pred_date_str)
                    matches = matches[
                        (matches["match_dt"].notna()) &
                        (matches["match_dt"] >= p_dt - pd.Timedelta(days=4)) &
                        (matches["match_dt"] <= p_dt + pd.Timedelta(days=4))
                    ]
                except Exception:
                    pass
            
            if not matches.empty:
                result_row = matches.iloc[-1]
                winner_canon = result_row["winner_name"]
                winner_name = p1_raw if winner_canon == p1_canon else p2_raw
                score = result_row.get("score", "")
                self.grade_match(pred["match_id"], actual_winner=winner_name, score=score)
                reconciled_count += 1
                
        return reconciled_count

    def get_pure_model_accuracy_table(self, include_pending: bool = True) -> pd.DataFrame:
        """
        Generate a clean dataframe comparing model predictions vs real outcomes
        COMPLETELY INDEPENDENT of odds, EV, stakes, or betting metrics.
        Includes both ATP and WTA matches.
        """
        if not self.predictions:
            return pd.DataFrame()

        target_preds = self.predictions if include_pending else [p for p in self.predictions if p.get("actual_winner") and p.get("status") != "VOID"]

        records = []
        for p in target_preds:
            if p.get("status") == "VOID":
                continue

            p1 = p["p1_name"]
            p2 = p["p2_name"]
            p1_prob = float(p.get("p1_prob", 50.0))
            p2_prob = float(p.get("p2_prob", 50.0))
            
            model_pick = p1 if p1_prob >= p2_prob else p2
            model_prob = max(p1_prob, p2_prob)
            winner = p.get("actual_winner")
            score = p.get("score")
            
            if winner:
                is_correct = (winner == model_pick)
                outcome_str = "✅ Correct" if is_correct else "❌ Incorrect"
                winner_display = winner
                score_display = score or "Completed"
            else:
                is_correct = None
                outcome_str = "⏳ Pending (In Play / Scheduled)"
                winner_display = "Pending"
                score_display = "Scheduled Today"

            if model_prob >= 70.0:
                conf_tier = "🔥 High (>70%)"
            elif model_prob >= 55.0:
                conf_tier = "⚡ Moderate (55-70%)"
            else:
                conf_tier = "⚖️ Toss-Up (<55%)"

            records.append({
                "Date": p.get("date", "N/A"),
                "Circuit": p.get("circuit", "ATP"),
                "Tournament": p.get("tourney_name", "N/A"),
                "Surface": p.get("surface", "Hard"),
                "Matchup": f"{p1} vs {p2}",
                "Model Pick": model_pick,
                "Model Win %": f"{model_prob:.1f}%",
                "Confidence Tier": conf_tier,
                "Actual Winner": winner_display,
                "Official Score": score_display,
                "Prediction Outcome": outcome_str,
                "is_correct": is_correct,
                "model_prob_num": model_prob,
                "status": p.get("status", "PENDING")
            })

        df = pd.DataFrame(records)
        return df.sort_values(by="Date", ascending=False)

    def get_pure_model_summary(self) -> Dict:
        """
        Calculate pure machine learning prediction accuracy and calibration metrics on completed matches.
        """
        table_df = self.get_pure_model_accuracy_table(include_pending=True)
        graded_df = table_df[table_df["is_correct"].notnull()]
        
        total_completed = len(graded_df)
        total_pending = len(table_df[table_df["is_correct"].isnull()])
        correct_matches = int(graded_df["is_correct"].sum()) if total_completed > 0 else 0
        accuracy_pct = round((correct_matches / total_completed) * 100, 1) if total_completed > 0 else 0.0

        graded_preds = [p for p in self.predictions if p.get("actual_winner") and p.get("status") not in ["VOID", "PENDING"]]
        brier_errors = []
        for p in graded_preds:
            w = p["actual_winner"]
            p1 = p["p1_name"]
            prob_winner = (float(p["p1_prob"]) / 100.0) if w == p1 else (float(p["p2_prob"]) / 100.0)
            brier_errors.append((1.0 - prob_winner) ** 2)
        brier_score = round(float(np.mean(brier_errors)), 4) if brier_errors else 0.0

        high_df = graded_df[graded_df["model_prob_num"] >= 70.0]
        high_conf_count = len(high_df)
        high_conf_acc = round((high_df["is_correct"].sum() / high_conf_count) * 100, 1) if high_conf_count > 0 else 0.0

        return {
            "total_matches": len(table_df),
            "total_completed": total_completed,
            "total_pending": total_pending,
            "correct_matches": correct_matches,
            "accuracy_pct": accuracy_pct,
            "brier_score": brier_score,
            "high_conf_accuracy": high_conf_acc,
            "high_conf_count": high_conf_count,
            "table_df": table_df,
        }

    def get_performance_summary(self) -> Dict:
        """
        Compute overall tracking statistics including betting PnL.
        """
        graded = [p for p in self.predictions if p.get("status") in ["WON", "LOST", "NO_BET"] and p.get("actual_winner")]
        if not graded:
            return {
                "total_graded": 0,
                "accuracy": 0.0,
                "brier_score": 0.0,
                "total_bets": 0,
                "bets_won": 0,
                "bet_win_rate": 0.0,
                "total_staked": 0.0,
                "total_pnl": 0.0,
                "roi": 0.0,
                "flat_pnl": 0.0,
                "flat_roi": 0.0,
                "history_df": pd.DataFrame(),
            }

        correct_count = sum(1 for p in graded if p.get("model_correct"))
        accuracy = (correct_count / len(graded)) * 100

        brier_errors = []
        for p in graded:
            w = p["actual_winner"]
            p1 = p["p1_name"]
            prob_winner = (float(p["p1_prob"]) / 100.0) if w == p1 else (float(p["p2_prob"]) / 100.0)
            brier_errors.append((1.0 - prob_winner) ** 2)
        brier_score = round(float(np.mean(brier_errors)), 4) if brier_errors else 0.0

        bets = [p for p in graded if p.get("status") in ["WON", "LOST"]]
        total_bets = len(bets)
        bets_won = sum(1 for p in bets if p.get("status") == "WON")
        bet_win_rate = (bets_won / total_bets * 100) if total_bets > 0 else 0.0
        
        total_staked = sum(float(p.get("best_stake", 0.0) or 0.0) for p in bets)
        total_pnl = sum(float(p.get("pnl", 0.0) or 0.0) for p in bets)
        roi = (total_pnl / total_staked * 100) if total_staked > 0 else 0.0

        total_flat_staked = total_bets * 20.0
        flat_pnl = sum(float(p.get("flat_pnl", 0.0) or 0.0) for p in bets)
        flat_roi = (flat_pnl / total_flat_staked * 100) if total_flat_staked > 0 else 0.0

        df_bets = pd.DataFrame(bets)
        if not df_bets.empty:
            df_bets["cum_pnl"] = df_bets["pnl"].cumsum()
            df_bets["cum_flat_pnl"] = df_bets["flat_pnl"].cumsum()

        return {
            "total_graded": len(graded),
            "accuracy": round(accuracy, 1),
            "brier_score": brier_score,
            "total_bets": total_bets,
            "bets_won": bets_won,
            "bet_win_rate": round(bet_win_rate, 1),
            "total_staked": round(total_staked, 2),
            "total_pnl": round(total_pnl, 2),
            "roi": round(roi, 1),
            "flat_pnl": round(flat_pnl, 2),
            "flat_roi": round(flat_roi, 1),
            "history_df": df_bets if not df_bets.empty else pd.DataFrame(),
        }
