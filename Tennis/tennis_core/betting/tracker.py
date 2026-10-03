"""Tennis prediction ledger: logging, result grading, ML accuracy and PnL/ROI tracking.

Ledger: ``Tennis/data/tracker/predictions_archive.json``, a JSON list of records.

Units (kept for compatibility with the predictor and the web payload):
* ``p1_prob``, ``p2_prob``, ``confidence``, ``best_ev`` and ``best_edge`` are PERCENT (60.6 == 60.6%).
* ``best_stake`` is a Kelly stake in currency on ``NOTIONAL_BANKROLL``; flat bets stake ``FLAT_STAKE``.
* ``score`` is always written from the winner's perspective ("6-4 3-6 7-5").

A record is a bet when it was logged with ``recommended_pick`` and ``best_stake > 0``.
Graded records (WON/LOST/VOID/NO_BET) are immutable, and predictions are frozen once
their match day has passed. This class is the only writer of the ledger file.
"""
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from tennis_core.config import PREDICTIONS_ARCHIVE_PATH
from tennis_core.utils.helpers import match_player_to_database, strip_accents
from sports_common.betting import bet_pnl
from sports_common.jsonstore import daily_backup, read_json, write_json_atomic

logger = logging.getLogger(__name__)

FLAT_STAKE = 20.0
GRADED_STATUSES = {"WON", "LOST", "VOID", "NO_BET"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _norm(name: Any) -> str:
    return strip_accents(str(name or "")).lower().strip()


def _same_player(a: Any, b: Any) -> bool:
    """Accent/case-insensitive equality, falling back to containment for 'J. Sinner' style names."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    return na == nb or na in nb or nb in na


class PredictionTracker:
    """Manages the lifecycle of predictions: creation, storage, outcome reconciliation, ML accuracy validation, and PnL tracking."""

    def __init__(self, archive_path: Path = PREDICTIONS_ARCHIVE_PATH):
        self.archive_path = Path(archive_path)
        self._batch_depth = 0
        self._dirty = False
        self.predictions: List[Dict] = self._load_predictions()

    def _load_predictions(self) -> List[Dict]:
        """Load the ledger; raises LedgerCorruptError rather than starting from an empty list."""
        data = read_json(self.archive_path, default=[], validate=lambda d: isinstance(d, list))
        return [p for p in data if isinstance(p, dict)]

    def _save_predictions(self):
        """Persist the ledger atomically (deferred until the end of an enclosing ``batch()``)."""
        if self._batch_depth > 0:
            self._dirty = True
            return
        daily_backup(self.archive_path)
        write_json_atomic(self.archive_path, self.predictions, default=str)
        self._dirty = False

    save = _save_predictions

    @contextmanager
    def batch(self):
        """Group many updates into a single write: ``with tracker.batch(): ...``."""
        self._batch_depth += 1
        try:
            yield self
        finally:
            self._batch_depth -= 1
            if self._batch_depth == 0 and self._dirty:
                self._save_predictions()

    def log_prediction(self, pred_dict: Dict) -> str:
        """
        Record a match prediction. Re-logging a pending match refreshes its prediction and
        prices until match day; graded or past matches are never modified.
        """
        match_id = pred_dict.get("match_id") or f"{pred_dict.get('circuit')}_{pred_dict.get('p1_name')}_{pred_dict.get('p2_name')}_{pred_dict.get('date')}"
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

        is_bet = bool(pred_dict.get("recommended_pick")) and float(pred_dict.get("best_stake") or 0.0) > 0
        now = _now_iso()

        if existing:
            if existing.get("status") in GRADED_STATUSES:
                return existing["match_id"]
            if str(existing.get("date") or "")[:10] < _today_utc():
                logger.debug(f"Match {existing.get('match_id')} has been played; its prediction is frozen.")
                return existing["match_id"]
            # Never let a refresh rewrite the record's identity or its first-seen prices.
            frozen = {k: existing[k] for k in ("match_id", "created_at", "opening_p1_odds", "opening_p2_odds", "first_pick") if existing.get(k) is not None}
            existing.update(pred_dict)
            existing.update(frozen)
            existing["updated_at"] = now
            if existing.get("opening_p1_odds") is None and pred_dict.get("p1_odds"):
                existing["opening_p1_odds"] = pred_dict.get("p1_odds")
                existing["opening_p2_odds"] = pred_dict.get("p2_odds")
            if existing.get("first_pick") is None and is_bet:
                existing["first_pick"] = self._pick_snapshot(pred_dict, now)
            match_id = existing["match_id"]
        else:
            record = {
                "match_id": match_id,
                "created_at": now,
                "status": "PENDING",  # PENDING, WON, LOST, VOID, NO_BET
                "actual_winner": None,
                "score": None,
                "pnl": 0.0,
                "flat_pnl": 0.0,
                **pred_dict,
                "updated_at": now,
                "opening_p1_odds": pred_dict.get("p1_odds"),
                "opening_p2_odds": pred_dict.get("p2_odds"),
                "first_pick": self._pick_snapshot(pred_dict, now) if is_bet else None,
            }
            record["match_id"] = match_id
            self.predictions.append(record)

        self._save_predictions()
        return match_id

    @staticmethod
    def _pick_snapshot(pred_dict: Dict, now: str) -> Dict[str, Any]:
        return {
            "pick": pred_dict.get("recommended_pick"),
            "odds": pred_dict.get("best_odds"),
            "ev_pct": pred_dict.get("best_ev"),
            "stake": pred_dict.get("best_stake"),
            "logged_at": now,
        }

    def grade_match(
        self,
        match_id: str,
        actual_winner: str,
        score: Optional[str] = None,
        total_games: Optional[int] = None,
        w_sets: Optional[int] = None,
        l_sets: Optional[int] = None,
        deciding_set: Optional[bool] = None,
    ) -> Optional[Dict]:
        """
        Grade a completed match: ML correctness, optional sets/games markets, and betting PnL.
        Only PENDING records are graded; anything already graded is returned unchanged.
        """
        match = next((p for p in self.predictions if p.get("match_id") == match_id), None)
        if not match:
            logger.warning(f"Match {match_id} not found in prediction archive.")
            return None
        if match.get("status") != "PENDING":
            return match

        p1_name = match["p1_name"]
        p2_name = match["p2_name"]
        match["graded_at"] = _now_iso()

        # Check if withdrawal / void
        if "void" in actual_winner.lower() or "withdrew" in actual_winner.lower():
            match.update({
                "actual_winner": "Void (Withdrawal)",
                "score": score or "Walkover",
                "status": "VOID",
                "model_correct": None,
                "pnl": 0.0,
                "flat_pnl": 0.0,
                "stake": 0.0,
                "is_value_bet": False,
            })
            self._save_predictions()
            return match

        # Resolve winner to exactly p1_name or p2_name (exact match first, then fuzzy)
        if _norm(actual_winner) == _norm(p1_name):
            winner_resolved = p1_name
        elif _norm(actual_winner) == _norm(p2_name):
            winner_resolved = p2_name
        else:
            winner_resolved = p1_name if _same_player(actual_winner, p1_name) else p2_name

        match["actual_winner"] = winner_resolved
        match["score"] = score

        # Pure ML Model Favorite (>50% model probability)
        p1_prob = float(match.get("p1_prob") or 50.0)
        p2_prob = float(match.get("p2_prob") or 50.0)
        predicted_fav = p1_name if p1_prob >= p2_prob else p2_name
        match["predicted_fav"] = predicted_fav
        match["fav_prob"] = max(p1_prob, p2_prob)
        match["model_correct"] = (winner_resolved == predicted_fav)
        match["correct_winner"] = match["model_correct"]

        if w_sets is not None and l_sets is not None and (w_sets + l_sets) > 0:
            self._grade_sets_and_games(match, winner_resolved == predicted_fav, total_games, w_sets, l_sets, deciding_set)

        # Betting PnL evaluation (Odds & Value Bets)
        rec_pick = match.get("recommended_pick")
        stake = float(match.get("best_stake") or 0.0)
        odds = float(match.get("best_odds") or 0.0)

        if rec_pick and stake > 0 and odds > 1.0:
            pick_won = _same_player(rec_pick, winner_resolved)
            match["status"] = "WON" if pick_won else "LOST"
            match["pnl"] = bet_pnl(stake, odds, pick_won)
            match["flat_pnl"] = bet_pnl(FLAT_STAKE, odds, pick_won)
            match["stake"] = stake
            match["is_value_bet"] = True
        else:
            match["status"] = "NO_BET"
            match["pnl"] = 0.0
            match["flat_pnl"] = 0.0
            match["stake"] = 0.0
            match["is_value_bet"] = False

        self._save_predictions()
        return match

    @staticmethod
    def _grade_sets_and_games(match: Dict, fav_won: bool, total_games: Optional[int],
                              w_sets: int, l_sets: int, deciding_set: Optional[bool]) -> None:
        """Grade the secondary markets stored in ``sets_games`` (favourite wins a set, games O/U, decider)."""
        fav_sets = w_sets if fav_won else l_sets
        match["correct_sets_at_least_1"] = fav_sets >= 1

        sg = match.get("sets_games") or {}
        exp_games = sg.get("expected_total_games")
        line = (sg.get("main_games_line") or {}).get("line")
        if total_games and exp_games is not None and line is not None:
            match["actual_games"] = int(total_games)
            match["games_line"] = float(line)
            match["exp_total_games"] = float(exp_games)
            match["correct_games_ou"] = (total_games > float(line)) == (float(exp_games) >= float(line))
            match["game_error"] = round(abs(float(exp_games) - total_games), 1)
        p_dec = sg.get("prob_deciding_set")
        if deciding_set is not None and p_dec is not None:
            match["correct_deciding_set"] = bool(deciding_set) == (float(p_dec) >= 50.0)

    def auto_reconcile(self, completed_matches_df: pd.DataFrame) -> int:
        """
        Automatically reconcile pending predictions against a dataframe of completed matches.
        Strictly enforces match date window (+- 4 days) to prevent matching future fixtures against historical encounters.
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

        with self.batch():
            for pred in self.predictions:
                if pred.get("status") != "PENDING" or not pred.get("date"):
                    continue

                p1_raw = pred["p1_name"]
                p2_raw = pred["p2_name"]

                p1_canon = match_player_to_database(p1_raw, known_players)
                p2_canon = match_player_to_database(p2_raw, known_players)

                matches = df_matches[
                    ((df_matches["winner_name"] == p1_canon) & (df_matches["loser_name"] == p2_canon)) |
                    ((df_matches["winner_name"] == p2_canon) & (df_matches["loser_name"] == p1_canon))
                ]
                if matches.empty:
                    continue

                try:
                    p_dt = pd.to_datetime(pred["date"])
                except (TypeError, ValueError):
                    continue
                matches = matches[
                    (matches["match_dt"].notna()) &
                    (matches["match_dt"] >= p_dt - pd.Timedelta(days=4)) &
                    (matches["match_dt"] <= p_dt + pd.Timedelta(days=4))
                ]

                if not matches.empty:
                    result_row = matches.iloc[-1]
                    winner_canon = result_row["winner_name"]
                    winner_name = p1_raw if winner_canon == p1_canon else p2_raw
                    score = result_row.get("score") or None
                    self.grade_match(pred["match_id"], actual_winner=winner_name, score=score)
                    reconciled_count += 1

        return reconciled_count

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
        brier_score = round(float(sum(brier_errors) / len(brier_errors)), 4) if brier_errors else 0.0

        bets = [p for p in graded if p.get("status") in ["WON", "LOST"]]
        total_bets = len(bets)
        bets_won = sum(1 for p in bets if p.get("status") == "WON")
        bet_win_rate = (bets_won / total_bets * 100) if total_bets > 0 else 0.0

        total_staked = sum(float(p.get("best_stake", 0.0) or 0.0) for p in bets)
        total_pnl = sum(float(p.get("pnl", 0.0) or 0.0) for p in bets)
        roi = (total_pnl / total_staked * 100) if total_staked > 0 else 0.0

        total_flat_staked = total_bets * FLAT_STAKE
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
