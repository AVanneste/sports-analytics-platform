"""Football prediction ledger: logging, result settlement, PnL and model verification.

Ledger: ``Football/data/cache/predictions_tracker.json``, a JSON list of records.

* Probabilities are fractions in [0, 1].
* A record is a bet when its latest pre-match ``best_pick`` carried value (``has_value``
  or positive EV). Flat bets stake ``FLAT_STAKE``; Kelly bets stake
  ``best_pick["kelly"] * NOTIONAL_BANKROLL``.
* ``opening_odds`` / ``first_pick`` are frozen at the first log, the top-level ``odds_*``
  fields hold the latest pre-match prices (a closing-line proxy for CLV).
* Settled records are immutable, and predictions are frozen once their match day has passed.
"""
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional
import pandas as pd

from football_core.config import TRACKER_FILE
from football_core.utils.helpers import normalize_team_name, teams_match
from sports_common.betting import NOTIONAL_BANKROLL, bet_pnl
from sports_common.jsonstore import daily_backup, read_json, write_json_atomic

logger = logging.getLogger(__name__)

FLAT_STAKE = 100.0
ODDS_FIELDS = (
    "odds_home", "odds_draw", "odds_away",
    "odds_over25", "odds_under25",
    "odds_btts_yes", "odds_btts_no",
    "odds_corners_over95", "odds_corners_under95",
    "odds_cards_over35", "odds_cards_under35",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _float_or_none(value: Any) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else f


def _int_or_none(value: Any) -> Optional[int]:
    f = _float_or_none(value)
    return None if f is None else int(f)


def _sum_or_none(*values: Optional[int]) -> Optional[int]:
    return None if any(v is None for v in values) else int(sum(values))


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
    for statistical model verification (accuracy, log loss, MAE, calibration)
    and betting analysis.
    """

    def __init__(self, storage_file: Path = TRACKER_FILE):
        self.storage_file = Path(storage_file)
        self.predictions: List[Dict[str, Any]] = []
        self._batch_depth = 0
        self._dirty = False
        self._load()

    def _load(self):
        """Load the ledger; raises LedgerCorruptError rather than starting from an empty list."""
        data = read_json(self.storage_file, default=[], validate=lambda d: isinstance(d, list))
        self.predictions = [p for p in data if isinstance(p, dict)]

    def save(self):
        """Persist the ledger atomically (deferred until the end of an enclosing ``batch()``)."""
        if self._batch_depth > 0:
            self._dirty = True
            return
        daily_backup(self.storage_file)
        write_json_atomic(self.storage_file, self.predictions)
        self._dirty = False

    @contextmanager
    def batch(self):
        """Group many updates into a single write: ``with tracker.batch(): ...``."""
        self._batch_depth += 1
        try:
            yield self
        finally:
            self._batch_depth -= 1
            if self._batch_depth == 0 and self._dirty:
                self.save()

    def upgrade_ledger(self) -> int:
        """Idempotently fill derived fields that older versions never wrote. Returns records changed.

        Only derived values are touched (Kelly stake/PnL from the stored pick, odds and
        result); predictions and results of settled records stay exactly as recorded.
        """
        changed = 0
        for pred in self.predictions:
            if pred.get("status") != "settled":
                continue
            pick = pred.get("best_pick") if isinstance(pred.get("best_pick"), dict) else {}
            odds = _float_or_none(pick.get("odds"))
            if pred.get("won") is not None and odds:
                kelly_stake = round((_float_or_none(pick.get("kelly")) or 0.0) * NOTIONAL_BANKROLL, 2)
                fields = {"kelly_stake": kelly_stake, "kelly_pnl": bet_pnl(kelly_stake, odds, pred["won"])}
            else:
                fields = {"kelly_stake": 0.0, "kelly_pnl": 0.0}
            if any(pred.get(k) != v for k, v in fields.items()):
                pred.update(fields)
                changed += 1
        if changed:
            self.save()
            logger.info(f"Upgraded {changed} settled ledger records (Kelly stake/PnL).")
        return changed

    def log_full_match_prediction(self, pred_item: Dict[str, Any]) -> bool:
        """
        Log a complete multi-category match prediction for statistical verification.
        Stores full model expectancies across 1X2, Goals, BTTS, Corners, Cards, and Scoreline.
        Returns True when a new record was created.
        """
        if not pred_item.get("home_team") or not pred_item.get("away_team"):
            logger.warning(f"Rejecting prediction log without valid home/away teams: {pred_item.get('match_id')}")
            return False

        probs = [_float_or_none(pred_item.get(k)) for k in ("prob_home", "prob_draw", "prob_away")]
        if any(p is None for p in probs):
            logger.warning(f"Rejecting prediction log without 1X2 probabilities: {pred_item.get('match_id')}")
            return False
        p_home, p_draw, p_away = probs

        meta = pred_item.get("fixture_meta", {})
        match_id = (
            meta.get("match_id")
            or pred_item.get("match_id")
            or f"{pred_item.get('league_key')}_{pred_item.get('home_team')}_{pred_item.get('away_team')}_{meta.get('date', pred_item.get('date', 'date'))}"
        )

        h_team = pred_item.get("home_team")
        a_team = pred_item.get("away_team")

        # The model's pick is simply its most likely outcome.
        if p_draw >= p_home and p_draw >= p_away:
            pred_1x2 = "Draw"
        elif p_home >= p_away:
            pred_1x2 = f"{h_team} Win"
        else:
            pred_1x2 = f"{a_team} Win"

        def _binary(prob_key: str, over_label: str, under_label: str):
            prob = _float_or_none(pred_item.get(prob_key))
            if prob is None:
                return None, None
            return prob, (over_label if prob >= 0.50 else under_label)

        p_o25, pred_o25 = _binary("prob_over25", "Over 2.5", "Under 2.5")
        p_btts, pred_btts = _binary("prob_btts_yes", "Yes", "No")
        p_corn_o95, pred_corn_o95 = _binary("prob_corners_over95", "Over 9.5", "Under 9.5")
        p_card_o35, pred_card_o35 = _binary("prob_cards_over35", "Over 3.5", "Under 3.5")

        def _complement(key: str, prob: Optional[float]) -> Optional[float]:
            explicit = _float_or_none(pred_item.get(key))
            if explicit is not None:
                return explicit
            return None if prob is None else 1.0 - prob

        xg_home = _float_or_none(pred_item.get("expected_goals_home"))
        xg_away = _float_or_none(pred_item.get("expected_goals_away"))
        exp_corners = _float_or_none(pred_item.get("expected_corners"))
        exp_cards = _float_or_none(pred_item.get("expected_cards"))

        ref_info = pred_item.get("referee", {})
        ref_name = ref_info.get("referee_name") if isinstance(ref_info, dict) else (str(ref_info) if ref_info else None)

        best_pick = pred_item.get("best_pick") if isinstance(pred_item.get("best_pick"), dict) else {}
        has_value = bool(pred_item.get("has_value")) if "has_value" in pred_item else bool((best_pick.get("ev") or 0) > 0)

        record = {
            "match_id": match_id,
            "date": meta.get("date") or pred_item.get("date") or _today_utc(),
            "league": pred_item.get("league_key") or pred_item.get("league"),
            "league_name": meta.get("league_name") or pred_item.get("league_name") or pred_item.get("league") or pred_item.get("league_key"),
            "home_team": h_team,
            "away_team": a_team,
            "referee": ref_name,

            # 1X2 Projections
            "prob_home": p_home,
            "prob_draw": p_draw,
            "prob_away": p_away,
            "pred_1x2": pred_1x2,

            # Goals Projections
            "expected_goals_home": xg_home,
            "expected_goals_away": xg_away,
            "exp_goals_home": xg_home,
            "exp_goals_away": xg_away,
            "exp_total_goals": (xg_home + xg_away) if (xg_home is not None and xg_away is not None) else None,
            "prob_over25": p_o25,
            "prob_under25": _complement("prob_under25", p_o25),
            "pred_over25": pred_o25,

            # BTTS Projections
            "prob_btts_yes": p_btts,
            "prob_btts_no": _complement("prob_btts_no", p_btts),
            "pred_btts": pred_btts,

            # Corners Projections
            "expected_corners": exp_corners,
            "exp_corners": exp_corners,
            "prob_corners_over95": p_corn_o95,
            "prob_corners_under95": _complement("prob_corners_under95", p_corn_o95),
            "pred_corners_o95": pred_corn_o95,

            # Cards Projections
            "expected_cards": exp_cards,
            "exp_cards": exp_cards,
            "prob_cards_over35": p_card_o35,
            "prob_cards_under35": _complement("prob_cards_under35", p_card_o35),
            "pred_cards_o35": pred_card_o35,

            # Scoreline
            "pred_score": pred_item.get("most_likely_score"),

            # Betting decision (latest pre-match view)
            "best_pick": best_pick or None,
            "market_category": best_pick.get("market") if best_pick else None,
            "has_value": has_value,
            "updated_at": _now_iso(),

            # Settlement Status
            "status": "pending",
            "actual_score": None,
            "actual_winner": None,
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

        # Market prices: only real quotes are written, so a fetch without odds never erases earlier ones.
        odds_snapshot = {k: _float_or_none(pred_item.get(k)) for k in ODDS_FIELDS}
        odds_snapshot = {k: v for k, v in odds_snapshot.items() if v and v > 1.0}
        if odds_snapshot:
            record.update(odds_snapshot)
            record["odds_captured_at"] = _now_iso()
            if pred_item.get("bookmaker"):
                record["bookmaker"] = pred_item["bookmaker"]

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
                if str(existing.get("date") or "")[:10] < _today_utc():
                    logger.debug(f"Match {match_id} has been played; its prediction is frozen.")
                    return False
                merged = {**existing, **record}
                merged["logged_at"] = existing.get("logged_at") or existing.get("created_at") or record["updated_at"]
                if not existing.get("opening_odds") and odds_snapshot:
                    merged["opening_odds"] = dict(odds_snapshot)
                if not existing.get("first_pick") and has_value and best_pick:
                    merged["first_pick"] = {**best_pick, "logged_at": record["updated_at"]}
                self.predictions[idx] = merged
                self.save()
                return False

        record["logged_at"] = record["updated_at"]
        record["opening_odds"] = dict(odds_snapshot) if odds_snapshot else None
        record["first_pick"] = {**best_pick, "logged_at": record["updated_at"]} if (has_value and best_pick) else None
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
            for k in ["prob_home", "prob_draw", "prob_away"]:
                if k in probs:
                    item[k] = probs[k]
            for src, dst in [("over25", "prob_over25"), ("under25", "prob_under25"),
                             ("btts_yes", "prob_btts_yes"), ("btts_no", "prob_btts_no")]:
                if src in probs:
                    item[dst] = probs[src]
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
            pred_win = str(item["predicted_winner"]).lower()
            side = "home" if "home" in pred_win else ("away" if "away" in pred_win else "draw")
            item["best_pick"] = {
                "market": "1X2",
                "selection": str(item["predicted_winner"]),
                "odds": item.get(f"odds_{side}"),
                "prob": item.get(f"prob_{side}"),
                "ev": 0.0,
                "kelly": 0.0,
            }

        return self.log_full_match_prediction(item)

    def _apply_result(
        self,
        pred: Dict[str, Any],
        fthg: int,
        ftag: int,
        actual_corners: Optional[int] = None,
        actual_cards: Optional[int] = None,
        actual_xg: Optional[float] = None,
        referee: Optional[str] = None,
    ) -> None:
        """Settle ``pred`` with a final score and (optional) corner/card totals."""
        score_str = f"{fthg}-{ftag}"
        total_goals = fthg + ftag
        actual_1x2_type = "Home" if fthg > ftag else ("Away" if ftag > fthg else "Draw")
        actual_btts = bool(fthg > 0 and ftag > 0)
        h_name = str(pred.get("home_team", "Home")).lower()
        a_name = str(pred.get("away_team", "Away")).lower()

        pred_1x2_clean = str(pred.get("pred_1x2") or "").strip()
        if actual_1x2_type == "Draw":
            correct_1x2 = ("draw" in pred_1x2_clean.lower() or pred_1x2_clean.lower() in ["x", "d"])
        elif actual_1x2_type == "Home":
            correct_1x2 = (pred_1x2_clean == f"{pred.get('home_team')} Win" or "home" in pred_1x2_clean.lower() or h_name in pred_1x2_clean.lower())
        else:
            correct_1x2 = (pred_1x2_clean == f"{pred.get('away_team')} Win" or "away" in pred_1x2_clean.lower() or a_name in pred_1x2_clean.lower())

        def _correct(pred_key: str, actual_label: str) -> Optional[bool]:
            predicted = pred.get(pred_key)
            return None if predicted is None else bool(predicted == actual_label)

        def _abs_error(exp_key: str, actual: Optional[int]) -> Optional[float]:
            expected = _float_or_none(pred.get(exp_key))
            return None if (expected is None or actual is None) else round(abs(expected - actual), 2)

        pred["status"] = "settled"
        pred["settled_at"] = _now_iso()
        pred["actual_score"] = score_str
        pred["actual_winner"] = f"{pred.get('home_team')} Win" if fthg > ftag else (f"{pred.get('away_team')} Win" if ftag > fthg else "Draw")
        pred["actual_goals"] = total_goals
        pred["actual_btts"] = "Yes" if actual_btts else "No"
        pred["actual_corners"] = actual_corners
        pred["actual_cards"] = actual_cards
        if actual_xg is not None:
            pred["actual_xg"] = round(float(actual_xg), 2)
        if referee and referee.strip():
            pred["referee"] = referee.strip()

        pred["correct_1x2"] = bool(correct_1x2)
        pred["correct_over25"] = _correct("pred_over25", "Over 2.5" if total_goals > 2.5 else "Under 2.5")
        pred["correct_btts"] = _correct("pred_btts", pred["actual_btts"])
        pred["correct_corners_o95"] = None if actual_corners is None else _correct("pred_corners_o95", "Over 9.5" if actual_corners > 9.5 else "Under 9.5")
        pred["correct_cards_o35"] = None if actual_cards is None else _correct("pred_cards_o35", "Over 3.5" if actual_cards > 3.5 else "Under 3.5")
        pred["correct_score"] = bool(pred.get("pred_score") == score_str)
        pred["goal_error"] = _abs_error("exp_total_goals", total_goals)
        pred["corner_error"] = _abs_error("exp_corners", actual_corners)
        pred["card_error"] = _abs_error("exp_cards", actual_cards)

        # Betting settlement (true value bets only)
        best_pick = pred.get("best_pick") if isinstance(pred.get("best_pick"), dict) else {}
        odds = _float_or_none(best_pick.get("odds"))
        is_bet = bool(odds and odds > 1.0) and (bool(pred.get("has_value")) or (best_pick.get("ev") or 0) > 0)
        needs_stat = {"Corners": actual_corners, "Cards": actual_cards}
        if is_bet and best_pick.get("market") in needs_stat and needs_stat[best_pick["market"]] is None:
            is_bet = False
            pred["bet_void_reason"] = f"{best_pick['market'].lower()} total unavailable"

        if is_bet:
            won_bet = bool(evaluate_best_pick_win(
                best_pick=best_pick,
                actual_1x2_type=actual_1x2_type,
                total_goals=total_goals,
                actual_btts=actual_btts,
                actual_corners=actual_corners,
                actual_cards=actual_cards,
                h_name=h_name,
                a_name=a_name,
            ))
            kelly_stake = round((_float_or_none(best_pick.get("kelly")) or 0.0) * NOTIONAL_BANKROLL, 2)
            pred["won"] = won_bet
            pred["stake"] = FLAT_STAKE
            pred["flat_pnl"] = bet_pnl(FLAT_STAKE, odds, won_bet)
            pred["kelly_stake"] = kelly_stake
            pred["kelly_pnl"] = bet_pnl(kelly_stake, odds, won_bet)
        else:
            pred["won"] = None
            pred["stake"] = 0.0
            pred["flat_pnl"] = 0.0
            pred["kelly_stake"] = 0.0
            pred["kelly_pnl"] = 0.0

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
                    pred_dt = pd.to_datetime(pred_date_str)
                    if pred_dt.tzinfo is not None:
                        pred_dt = pred_dt.tz_localize(None)
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

            row = team_matches.iloc[-1]
            fthg = _int_or_none(row.get("FTHG"))
            ftag = _int_or_none(row.get("FTAG"))
            if fthg is None or ftag is None:
                continue
            corners = _sum_or_none(_int_or_none(row.get("HC")), _int_or_none(row.get("AC")))
            cards = _sum_or_none(*(_int_or_none(row.get(c)) for c in ("HY", "AY", "HR", "AR")))
            self._apply_result(pred, fthg, ftag, actual_corners=corners, actual_cards=cards)
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
        """Settle one pending prediction with real scores & stats. Settled records are never re-graded."""
        pred = next((p for p in self.predictions if p.get("match_id") == match_id), None)
        if not pred or pred.get("status") == "settled":
            return False

        corners = (hc + ac) if (hc is not None and ac is not None) else None
        self._apply_result(pred, int(fthg), int(ftag), actual_corners=corners, actual_cards=cards,
                           actual_xg=actual_xg, referee=referee)
        self.save()
        return True
