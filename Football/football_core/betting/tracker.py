"""Prediction Archive, Result Reconciliation, Model Verification & Accuracy Engine."""
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np

from football_core.config import TRACKER_FILE
from football_core.utils.helpers import normalize_team_name, teams_match

logger = logging.getLogger(__name__)


def evaluate_best_pick_win(
    best_pick: Dict[str, Any],
    actual_1x2_type: str,
    total_goals: int,
    actual_btts: bool,
    actual_corners: Optional[int] = None,
    actual_cards: Optional[int] = None,
    h_name: str = "",
    a_name: str = ""
) -> bool:
    """Accurately determine if the recommended value bet (best_pick) won."""
    market = best_pick.get("market") or "1X2"
    selection = str(best_pick.get("selection") or "").strip().lower()
    
    if market == "1X2":
        act_str = str(actual_1x2_type).strip().lower()
        is_actual_draw = ("draw" in act_str or act_str in ["x", "d"])
        is_actual_away = ("away" in act_str or (bool(a_name) and a_name.lower() in act_str) or act_str in ["2", "a"])
        is_actual_home = ("home" in act_str or (bool(h_name) and h_name.lower() in act_str) or act_str in ["1", "h"])

        if "draw" in selection or selection in ["x", "draw", "d"]:
            return is_actual_draw
        elif "away" in selection or (bool(a_name) and a_name.lower() in selection):
            return is_actual_away
        elif "home" in selection or (bool(h_name) and h_name.lower() in selection) or "1" in selection:
            return is_actual_home
        elif "(fav)" in selection:
            if bool(a_name) and a_name.lower() in selection:
                return is_actual_away
            return is_actual_home
        return False
    elif market in ["Goals", "Totals"]:
        if "over" in selection:
            return total_goals > 2.5
        elif "under" in selection:
            return total_goals < 2.5
        return False
    elif market == "BTTS":
        if "yes" in selection:
            return bool(actual_btts)
        elif "no" in selection:
            return not bool(actual_btts)
        return False
    elif market == "Corners":
        if actual_corners is not None:
            return (actual_corners > 9.5) if "over" in selection else (actual_corners < 9.5)
        return False
    elif market == "Cards":
        if actual_cards is not None:
            return (actual_cards > 3.5) if "over" in selection else (actual_cards < 3.5)
        return False
    return False


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
                    raw_data = json.load(f)
                    self.predictions = [
                        p for p in raw_data
                        if isinstance(p, dict) and (p.get("status") == "settled" or (p.get("home_team") and p.get("away_team")))
                    ]
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
        if not pred_item.get("home_team") or not pred_item.get("away_team"):
            logger.warning(f"Rejecting prediction log without valid home/away teams: {pred_item.get('match_id')}")
            return False

        meta = pred_item.get("fixture_meta", {})
        match_id = (
            meta.get("match_id")
            or pred_item.get("match_id")
            or f"{pred_item.get('league_key')}_{pred_item.get('home_team')}_{pred_item.get('away_team')}_{meta.get('date', pred_item.get('date', 'date'))}"
        )
        
        p_home = float(pred_item.get("prob_home", 0.33))
        p_draw = float(pred_item.get("prob_draw", 0.33))
        p_away = float(pred_item.get("prob_away", 0.33))
        
        mls = str(pred_item.get("most_likely_score", ""))
        h_team = pred_item.get("home_team", "Home")
        a_team = pred_item.get("away_team", "Away")

        # Intelligent Draw condition for closely-matched fixtures
        is_draw = (p_draw >= p_home and p_draw >= p_away) or \
                  (abs(p_home - p_away) <= 0.07 and p_draw >= 0.26) or \
                  (mls in ["1-1", "0-0"] and abs(p_home - p_away) <= 0.09)

        if is_draw:
            pred_1x2 = "Draw"
        elif p_home >= p_away:
            pred_1x2 = f"{h_team} Win"
        else:
            pred_1x2 = f"{a_team} Win"

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
            "date": meta.get("date") or pred_item.get("date", str(pd.Timestamp.now().date())),
            "league": pred_item.get("league_key") or pred_item.get("league"),
            "league_name": meta.get("league_name") or pred_item.get("league_name") or pred_item.get("league") or pred_item.get("league_key"),
            "home_team": pred_item.get("home_team"),
            "away_team": pred_item.get("away_team"),
            "referee": ref_name,
            
            # 1X2 Projections
            "prob_home": p_home,
            "prob_draw": p_draw,
            "prob_away": p_away,
            "pred_1x2": pred_1x2,

            # Goals Projections
            "expected_goals_home": float(pred_item.get("expected_goals_home", 1.3)),
            "expected_goals_away": float(pred_item.get("expected_goals_away", 1.1)),
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
            "expected_corners": float(pred_item.get("expected_corners", 9.5)),
            "exp_corners": float(pred_item.get("expected_corners", 9.5)),
            "prob_corners_over95": p_corn_o95,
            "prob_corners_under95": float(pred_item.get("prob_corners_under95", 1.0 - p_corn_o95)),
            "pred_corners_o95": pred_corn_o95,

            # Cards Projections
            "expected_cards": float(pred_item.get("expected_cards", 4.2)),
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

        # Check if already logged - strictly immutable for settled records
        for idx, existing in enumerate(self.predictions):
            existing_id = existing.get("match_id")
            is_same = (existing_id == match_id) or (
                existing.get("league") == record.get("league")
                and existing.get("home_team") == record.get("home_team")
                and existing.get("away_team") == record.get("away_team")
                and str(existing.get("date"))[:10] == str(record.get("date"))[:10]
            )
            if is_same:
                if existing.get("status") == "settled":
                    logger.debug(f"Match {match_id} is already settled. Skipping update.")
                    return False
                self.predictions[idx] = {**existing, **record}
                self.save()
                return False

        self.predictions.append(record)
        self.save()
        return True

    def log_prediction(self, pred_item: Dict[str, Any]) -> bool:
        """
        Standard prediction logging method.
        Normalizes top-level fields (match_id, date, league_key, home_team, away_team,
        predicted_winner, probabilities, odds) and delegates to log_full_match_prediction.
        Guarantees that settled entries (status == 'settled') are never overwritten or mutated.
        """
        item = dict(pred_item)

        # Normalize fixture metadata
        meta = dict(item.get("fixture_meta", {}))
        if "match_id" in item and "match_id" not in meta:
            meta["match_id"] = item["match_id"]
        if "date" in item and "date" not in meta:
            meta["date"] = item["date"]
        if "league_name" in item and "league_name" not in meta:
            meta["league_name"] = item["league_name"]
        elif "league" in item and "league_name" not in meta:
            meta["league_name"] = item["league"]
        item["fixture_meta"] = meta

        # Normalize league_key
        if "league_key" not in item:
            item["league_key"] = item.get("league") or meta.get("league_key", "EPL")

        # Normalize probabilities if passed as nested dict or list
        if "probabilities" in item and isinstance(item["probabilities"], dict):
            probs = item["probabilities"]
            for k in ["home", "draw", "away"]:
                if k in probs:
                    item[f"prob_{k}"] = probs[k]
            if "prob_home" in probs:
                item["prob_home"] = probs["prob_home"]
            if "prob_draw" in probs:
                item["prob_draw"] = probs["prob_draw"]
            if "prob_away" in probs:
                item["prob_away"] = probs["prob_away"]
            if "over25" in probs:
                item["prob_over25"] = probs["over25"]
            if "under25" in probs:
                item["prob_under25"] = probs["under25"]
            if "btts_yes" in probs:
                item["prob_btts_yes"] = probs["btts_yes"]
            if "btts_no" in probs:
                item["prob_btts_no"] = probs["btts_no"]
        elif "probabilities" in item and isinstance(item["probabilities"], (list, tuple)) and len(item["probabilities"]) >= 3:
            item["prob_home"] = float(item["probabilities"][0])
            item["prob_draw"] = float(item["probabilities"][1])
            item["prob_away"] = float(item["probabilities"][2])

        # Normalize odds if passed as nested dict
        if "odds" in item and isinstance(item["odds"], dict):
            odds_dict = item["odds"]
            for k in ["home", "draw", "away", "over25", "under25", "btts_yes", "btts_no"]:
                if k in odds_dict:
                    item[f"odds_{k}"] = odds_dict[k]
                elif f"odds_{k}" in odds_dict:
                    item[f"odds_{k}"] = odds_dict[f"odds_{k}"]

        # Normalize predicted_winner if given
        if "predicted_winner" in item and "best_pick" not in item:
            pred_win = str(item["predicted_winner"])
            item["best_pick"] = {
                "market": "1X2",
                "selection": pred_win,
                "odds": item.get("odds_home") if "home" in pred_win.lower() else (item.get("odds_away") if "away" in pred_win.lower() else item.get("odds_draw")),
                "prob": item.get("prob_home") if "home" in pred_win.lower() else (item.get("prob_away") if "away" in pred_win.lower() else item.get("prob_draw", 0.33)),
                "ev": 0.0,
                "kelly": 0.0,
            }

        return self.log_full_match_prediction(item)

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

            # Fast filter by date window (+/- 4 days) first to reduce 23,000 rows to ~30 rows
            df_window = completed_df
            if pred_date_str:
                try:
                    pred_dt = pd.to_datetime(pred_date_str).tz_localize(None) if hasattr(pd.to_datetime(pred_date_str), "tz_localize") else pd.to_datetime(pred_date_str)
                    df_window = completed_df[
                        (completed_df["Date"] >= (pred_dt - pd.Timedelta(days=4))) &
                        (completed_df["Date"] <= (pred_dt + pd.Timedelta(days=4)))
                    ]
                except Exception:
                    df_window = completed_df

            if df_window.empty:
                continue

            h_norm = normalize_team_name(h)
            a_norm = normalize_team_name(a)

            # Match team names within the date window
            team_matches = df_window[
                ((df_window["HomeTeam"] == h) | (df_window["HomeTeam"] == h_norm) |
                 df_window["HomeTeam"].apply(lambda t: teams_match(t, h) or teams_match(t, h_norm))) &
                ((df_window["AwayTeam"] == a) | (df_window["AwayTeam"] == a_norm) |
                 df_window["AwayTeam"].apply(lambda t: teams_match(t, a) or teams_match(t, a_norm)))
            ]

            if team_matches.empty:
                continue

            match_row = team_matches

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

                pred_1x2_clean = str(pred.get("pred_1x2", "")).strip()
                if actual_1x2_type == "Draw":
                    correct_1x2 = ("draw" in pred_1x2_clean.lower() or pred_1x2_clean.lower() in ["x", "d"])
                elif actual_1x2_type == "Home":
                    correct_1x2 = (pred_1x2_clean == f"{pred.get('home_team')} Win" or "home" in pred_1x2_clean.lower() or h_name in pred_1x2_clean.lower())
                else:
                    correct_1x2 = (pred_1x2_clean == f"{pred.get('away_team')} Win" or "away" in pred_1x2_clean.lower() or a_name in pred_1x2_clean.lower())

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

                # Betting calculation (evaluate true value bets only)
                best_pick = pred.get("best_pick", {})
                has_val = bool(pred.get("has_value")) or (isinstance(best_pick, dict) and (best_pick.get("ev") or 0) > 0)
                if has_val and best_pick and best_pick.get("odds"):
                    odds = float(best_pick.get("odds", 1.0) or 1.0)
                    won_bet = evaluate_best_pick_win(
                        best_pick=best_pick,
                        actual_1x2_type=actual_1x2_type,
                        total_goals=total_goals,
                        actual_btts=actual_btts,
                        actual_corners=actual_corners,
                        actual_cards=actual_cards,
                        h_name=h_name,
                        a_name=a_name
                    )
                    pred["won"] = bool(won_bet)
                    pred["flat_pnl"] = round(float((100.0 * (odds - 1.0)) if won_bet else -100.0), 2)
                else:
                    pred["won"] = None
                    pred["flat_pnl"] = 0.0

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
        hc: Optional[int] = None, 
        ac: Optional[int] = None, 
        cards: Optional[int] = None,
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
        
        actual_corners = (hc + ac) if (hc is not None and ac is not None) else None
        actual_cards = cards if cards is not None else None

        h_name = str(pred.get("home_team", "Home")).lower()
        a_name = str(pred.get("away_team", "Away")).lower()
        pred_1x2_clean = str(pred.get("pred_1x2", "")).strip()
        if actual_1x2_type == "Draw":
            correct_1x2 = ("draw" in pred_1x2_clean.lower() or pred_1x2_clean.lower() in ["x", "d"])
        elif actual_1x2_type == "Home":
            correct_1x2 = (pred_1x2_clean == f"{pred.get('home_team')} Win" or "home" in pred_1x2_clean.lower() or h_name in pred_1x2_clean.lower())
        else:
            correct_1x2 = (pred_1x2_clean == f"{pred.get('away_team')} Win" or "away" in pred_1x2_clean.lower() or a_name in pred_1x2_clean.lower())

        pred_o25 = pred.get("pred_over25", "Over 2.5")
        actual_o25 = "Over 2.5" if total_goals > 2.5 else "Under 2.5"
        correct_o25 = (pred_o25 == actual_o25)

        pred_btts = pred.get("pred_btts", "Yes")
        actual_btts_str = "Yes" if actual_btts else "No"
        correct_btts = (pred_btts == actual_btts_str)

        if actual_corners is not None:
            pred_corn = pred.get("pred_corners_o95", "Over 9.5")
            actual_corn_str = "Over 9.5" if actual_corners > 9.5 else "Under 9.5"
            correct_corn = bool(pred_corn == actual_corn_str)
            corn_err = round(abs(float(pred.get("exp_corners", 9.5)) - actual_corners), 2)
        else:
            correct_corn = None
            corn_err = None

        if actual_cards is not None:
            pred_cards = pred.get("pred_cards_o35", "Over 3.5")
            actual_cards_str = "Over 3.5" if actual_cards > 3.5 else "Under 3.5"
            correct_cards = bool(pred_cards == actual_cards_str)
            card_err = round(abs(float(pred.get("exp_cards", 4.2)) - actual_cards), 2)
        else:
            correct_cards = None
            card_err = None

        goal_err = abs(float(pred.get("exp_total_goals", 2.5)) - total_goals)
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
        pred["correct_corners_o95"] = correct_corn
        pred["correct_cards_o35"] = correct_cards
        pred["correct_score"] = bool(correct_score)
        pred["goal_error"] = round(float(goal_err), 2)
        pred["corner_error"] = corn_err
        pred["card_error"] = card_err

        # Betting calculation (evaluate true value bets only)
        best_pick = pred.get("best_pick", {})
        has_val = bool(pred.get("has_value")) or (isinstance(best_pick, dict) and (best_pick.get("ev") or 0) > 0)
        if has_val and best_pick and best_pick.get("odds"):
            odds = float(best_pick.get("odds", 1.0) or 1.0)
            won_bet = evaluate_best_pick_win(
                best_pick=best_pick,
                actual_1x2_type=actual_1x2_type,
                total_goals=total_goals,
                actual_btts=actual_btts,
                actual_corners=actual_corners,
                actual_cards=actual_cards,
                h_name=h_name,
                a_name=a_name
            )
            pred["won"] = bool(won_bet)
            pred["flat_pnl"] = round(float((100.0 * (odds - 1.0)) if won_bet else -100.0), 2)
        else:
            pred["won"] = None
            pred["flat_pnl"] = 0.0

        self.save()
        return True
