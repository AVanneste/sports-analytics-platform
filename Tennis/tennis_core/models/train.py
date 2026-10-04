"""Tennis model training, calibration and honest holdout evaluation.

Rows come in mirrored pairs (winner-as-p1, loser-as-p1), so every split and calibration fold
is cut on match boundaries: a match and its mirror never land on different sides of a split.
Models are fitted on the first 70% of matches, the next 15% is the validation window, and all
reported metrics come from the last 15%. The deployed model is then refitted on every match.
"""
import logging
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss, roc_auc_score

from tennis_core.config import ATP_MODEL_PATH, WTA_MODEL_PATH, METRICS_PATH, MODELS_DIR, MIN_VALUE_THRESHOLD, TRAIN_FROM_YEAR
from tennis_core.features.builder import FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION, TennisFeaturePipeline
from sports_common.betting import DEFAULT_MARKET_MODEL_WEIGHT, MAX_CREDIBLE_EV, backtest_value_bets
from sports_common.evaluation import blend, compare_to_market, devig, fit_market_blend_weight, paired_difference
from sports_common.jsonstore import read_json, write_json_atomic

logger = logging.getLogger(__name__)

TRAIN_FRACTION, VALIDATION_FRACTION = 0.70, 0.15
UNINFORMED_LOG_LOSS = math.log(2)


def holdout_market_report(X_test: pd.DataFrame, y_test: pd.Series, p1_probs: np.ndarray) -> Dict:
    """Compare holdout P(p1 wins) with vig-free pre-match prices, when the rows carry them."""
    if not {"p1_odds", "p2_odds"}.issubset(X_test.columns):
        return {}
    market, keep = [], []
    for o1, o2 in X_test[["p1_odds", "p2_odds"]].itertuples(index=False):
        m = devig([o1, o2])
        keep.append(m is not None)
        market.append(m[0] if m is not None else np.nan)
    keep = np.asarray(keep, dtype=bool)
    if not keep.any():
        return {}
    return {"holdout_vs_market": compare_to_market(
        np.asarray(p1_probs)[keep], np.asarray(market)[keep], y_test.to_numpy(dtype=int)[keep])}


def _market_p1(X_rows: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    """Vig-free P(p1 wins) per row and a mask of rows with two real prices."""
    if not {"p1_odds", "p2_odds"}.issubset(X_rows.columns):
        return np.full(len(X_rows), np.nan), np.zeros(len(X_rows), dtype=bool)
    market, keep = [], []
    for o1, o2 in X_rows[["p1_odds", "p2_odds"]].itertuples(index=False):
        m = devig([o1, o2])
        keep.append(m is not None)
        market.append(m[0] if m is not None else np.nan)
    return np.asarray(market, dtype=float), np.asarray(keep, dtype=bool)


def fit_market_weight(X_rows: pd.DataFrame, y_rows: pd.Series, p1_probs: np.ndarray, min_rows: int = 100) -> float:
    """Weight on the model vs the vig-free price that minimises validation log loss."""
    market, keep = _market_p1(X_rows)
    if keep.sum() < min_rows:
        return DEFAULT_MARKET_MODEL_WEIGHT
    return fit_market_blend_weight(np.asarray(p1_probs)[keep], market[keep], y_rows.to_numpy(dtype=int)[keep])["weight"]


def blend_vs_market(X_rows: pd.DataFrame, row_probs: np.ndarray, market_weight: float, min_matches: int = 100) -> Dict:
    """Per-match log-loss difference of the model/market blend vs the market alone (mirrored test rows;
    each match uses the antisymmetric average of its two rows, as the live predictor does)."""
    winner_view, loser_view = np.asarray(row_probs)[0::2], np.asarray(row_probs)[1::2]
    n = min(len(winner_view), len(loser_view))
    p_winner = (winner_view[:n] + 1.0 - loser_view[:n]) / 2.0
    market, keep = _market_p1(X_rows.iloc[0::2].iloc[:n])
    if keep.sum() < min_matches:
        return {}
    blended = blend(p_winner[keep], market[keep], market_weight)
    loss = lambda p: -np.log(np.clip(p, 1e-12, 1.0))
    return paired_difference(loss(blended), loss(market[keep]))


def value_bet_backtest(X_rows: pd.DataFrame, row_probs: np.ndarray, market_weight: float) -> Dict:
    """Flat-stake backtest on mirrored test rows (even rows have the winner as p1).

    Each match uses the antisymmetric average of its two rows, as the live predictor does.
    """
    winner_view = np.asarray(row_probs)[0::2]
    loser_view = np.asarray(row_probs)[1::2]
    n = min(len(winner_view), len(loser_view))
    p_winner = (winner_view[:n] + (1.0 - loser_view[:n])) / 2.0
    rows = X_rows.iloc[0::2].iloc[:n]
    market, keep = _market_p1(rows)
    if not keep.any():
        return {}
    odds = rows.loc[keep, ["p1_odds", "p2_odds"]].to_numpy(dtype=float)
    raw = np.column_stack([p_winner[keep], 1.0 - p_winner[keep]])
    blended_w = blend(p_winner[keep], market[keep], market_weight)
    blended = np.column_stack([blended_w, 1.0 - blended_w])
    outcomes = np.zeros(int(keep.sum()), dtype=int)  # selection 0 is always the actual winner
    return {
        "backtest_model_only": backtest_value_bets(raw, odds, outcomes, min_ev=MIN_VALUE_THRESHOLD),
        "backtest_market_aware": backtest_value_bets(blended, odds, outcomes, min_ev=MIN_VALUE_THRESHOLD,
                                                     max_ev=MAX_CREDIBLE_EV),
    }


def paired_boundary(n_rows: int, fraction: float) -> int:
    """Row index at ``fraction`` of the data, rounded down to a match (pair) boundary."""
    return int((n_rows // 2) * fraction) * 2


def paired_time_series_cv(n_rows: int, n_splits: int = 3) -> List[Tuple[np.ndarray, np.ndarray]]:
    """Expanding-window folds (like TimeSeriesSplit) whose boundaries never split a mirrored pair."""
    n_matches = n_rows // 2
    fold = n_matches // (n_splits + 1)
    splits = []
    for k in range(1, n_splits + 1):
        train_end = fold * k * 2
        test_end = min(fold * (k + 1) * 2, n_rows) if k < n_splits else n_rows
        splits.append((np.arange(0, train_end), np.arange(train_end, test_end)))
    return splits


def _new_lgbm() -> lgb.LGBMClassifier:
    # One thread, as for football (football_core.models.estimators): as fast on this data,
    # deterministic, and safe inside parallel backtests.
    return lgb.LGBMClassifier(
        n_estimators=250, learning_rate=0.03, num_leaves=31, max_depth=6, subsample=0.8,
        colsample_bytree=0.8, min_child_samples=20, random_state=42, verbosity=-1, n_jobs=1,
    )


def _fit_calibrated(X: pd.DataFrame, y: pd.Series) -> CalibratedClassifierCV:
    model = CalibratedClassifierCV(estimator=_new_lgbm(), method="sigmoid", cv=paired_time_series_cv(len(X)))
    return model.fit(X, y)


def train_tennis_model(
    X: pd.DataFrame,
    y: pd.Series,
    circuit: str,
) -> Tuple[CalibratedClassifierCV, Dict]:
    """Train the calibrated LightGBM match-winner model; return (deployed model, holdout metrics)."""
    if "match_date" in X.columns:  # earlier seasons only warm the ratings and form up
        keep = (pd.to_datetime(X["match_date"]) >= pd.Timestamp(f"{TRAIN_FROM_YEAR}-01-01")).to_numpy()
        X, y = X[keep].reset_index(drop=True), y[keep].reset_index(drop=True)
    if X.empty or len(X) < 200:
        raise ValueError(f"Insufficient training data for {circuit}: {len(X)} samples")

    feature_cols = [c for c in FEATURE_COLUMNS if c in X.columns]
    X_features = X[feature_cols]  # missing values stay NaN; LightGBM handles them natively

    i_val = paired_boundary(len(X), TRAIN_FRACTION)
    i_test = paired_boundary(len(X), TRAIN_FRACTION + VALIDATION_FRACTION)
    X_train, y_train = X_features.iloc[:i_val], y.iloc[:i_val]
    X_test, y_test = X_features.iloc[i_test:], y.iloc[i_test:]

    logger.info(f"Training {circuit.upper()} model: {len(X_train)} train rows, "
                f"{i_test - i_val} validation rows, {len(X_test)} test rows")
    fitted = _fit_calibrated(X_train, y_train)

    # Model-vs-market weight chosen on the validation window
    p_val = fitted.predict_proba(X_features.iloc[i_val:i_test])[:, 1]
    market_weight = fit_market_weight(X.iloc[i_val:i_test], y.iloc[i_val:i_test], p_val)

    # Evaluation on the untouched, out-of-time test window
    y_pred_proba = fitted.predict_proba(X_test)[:, 1]
    # Value picks only if blending the model in actually beat the market there, beyond noise
    blend_check = blend_vs_market(X.iloc[i_test:], y_pred_proba, market_weight)
    market_validated = bool(market_weight > 0 and blend_check and blend_check["mean"] + 2 * blend_check["se"] < 0)
    acc = float(accuracy_score(y_test, (y_pred_proba >= 0.5).astype(int)))
    auc = float(roc_auc_score(y_test, y_pred_proba))
    ll = float(log_loss(y_test, y_pred_proba))
    brier = float(brier_score_loss(y_test, y_pred_proba))

    # Deployed model sees every match; importances from an uncalibrated fit on the same data
    calibrated_model = _fit_calibrated(X_features, y)
    base = _new_lgbm().fit(X_features, y)
    importances = dict(sorted(zip(feature_cols, (float(v) for v in base.feature_importances_)),
                              key=lambda item: item[1], reverse=True))

    metrics = {
        "circuit": circuit.upper(),
        "schema_version": FEATURE_SCHEMA_VERSION,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_end": str(pd.Timestamp(X["match_date"].max()).date()) if "match_date" in X else None,
        "total_samples": len(X),
        "train_samples": len(X_train),
        "test_samples": len(X_test),
        "accuracy": round(acc * 100, 2),
        "roc_auc": round(auc, 4),
        "log_loss": round(ll, 4),
        "brier_score": round(brier, 4),
        "feature_importances": importances,
        "market_weight": market_weight,
        "holdout_blend_vs_market": blend_check,
        "market_validated": market_validated,
        **holdout_market_report(X.iloc[i_test:], y_test, y_pred_proba),
        **value_bet_backtest(X.iloc[i_test:], y_pred_proba, market_weight),
    }

    logger.info(f"[{circuit.upper()} Evaluation] Accuracy: {metrics['accuracy']}%, AUC: {metrics['roc_auc']}, "
                f"log loss: {metrics['log_loss']}"
                + (f" vs market {metrics['holdout_vs_market']['market_log_loss']}" if "holdout_vs_market" in metrics else ""))
    return calibrated_model, metrics


def _model_path(circuit: str):
    return ATP_MODEL_PATH if circuit.lower() == "atp" else WTA_MODEL_PATH


def save_trained_pipeline(pipeline: Optional[TennisFeaturePipeline], model: Optional[CalibratedClassifierCV],
                          metrics: Dict, circuit: str):
    """Save the model and/or feature pipeline state to disk and record the metrics."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    if model is not None:
        joblib.dump(model, _model_path(circuit), compress=3)
    if pipeline is not None:
        joblib.dump(pipeline, MODELS_DIR / f"{circuit.lower()}_pipeline.pkl", compress=3)

    all_metrics = read_json(METRICS_PATH, default={}) or {}
    all_metrics[circuit.lower()] = metrics
    write_json_atomic(METRICS_PATH, all_metrics)
    logger.info(f"Saved {circuit.upper()} artifacts to {MODELS_DIR}")


def retrain_circuit(circuit: str, cleaned_df: pd.DataFrame, gate: bool = True) -> Dict:
    """Rebuild features and retrain one circuit, keeping the deployed model if the candidate is worse.

    The feature pipeline (ratings, form, serve/return state) is always refreshed; only the
    classifier is subject to the promotion gate.
    """
    from sports_common.evaluation import should_promote

    pipeline = TennisFeaturePipeline(circuit=circuit)
    X, y = pipeline.process_historical_matches(cleaned_df)
    model, metrics = train_tennis_model(X, y, circuit=circuit)

    current_metrics = (read_json(METRICS_PATH, default={}) or {}).get(circuit.lower())
    promote, reason = should_promote(metrics, current_metrics, "holdout_vs_market",
                                     FEATURE_SCHEMA_VERSION, UNINFORMED_LOG_LOSS)
    if not gate or promote or not _model_path(circuit).exists():
        save_trained_pipeline(pipeline, model, metrics, circuit)
        return {"circuit": circuit, "status": "promoted", "reason": reason if gate else "gate disabled"}

    kept = dict(current_metrics)
    kept["rejected_candidate"] = {k: v for k, v in metrics.items() if k != "feature_importances"}
    kept["checked_at"] = metrics["trained_at"]
    save_trained_pipeline(pipeline, None, kept, circuit)
    logger.warning(f"[{circuit.upper()}] Kept the deployed model: {reason}")
    return {"circuit": circuit, "status": "kept_current", "reason": reason}
