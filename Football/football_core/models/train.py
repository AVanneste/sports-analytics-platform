"""Model training, calibration and honest holdout evaluation for domestic football leagues.

Chronological split: models are fitted on the first 70% of matches, the ML/Dixon-Coles blend
weights are chosen on the next 15% (validation), and every reported metric comes from the last
15% (test), which nothing was fitted on. The deployed models are then refitted on all matches.
"""
import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd

from football_core.config import MAX_VALUE_ODDS, MIN_VALUE_PROB, MIN_VALUE_THRESHOLD, MODELS_DIR, PROCESSED_DATA_DIR
from football_core.features.builder import FEATURE_SCHEMA_VERSION, FootballFeaturePipeline
from football_core.models.estimators import fit_outcome_models
from sports_common.betting import DEFAULT_MARKET_MODEL_WEIGHT, MAX_CREDIBLE_EV, backtest_value_bets
from sports_common.evaluation import blend, compare_to_market, devig, fit_market_blend_weight, log_loss
from sports_common.jsonstore import read_json, write_json_atomic

logger = logging.getLogger(__name__)

METRICS_FILE = PROCESSED_DATA_DIR / "model_metrics.json"
TRAIN_FRACTION, VALIDATION_FRACTION = 0.70, 0.15
MIN_TRAINING_ROWS = 200
UNINFORMED_LOG_LOSS_1X2 = math.log(3)


def market_probabilities(frame: pd.DataFrame, odds_cols: List[str]) -> Tuple[np.ndarray, np.ndarray]:
    """Vig-free market probabilities per row plus a mask of rows where every price was usable."""
    if not set(odds_cols).issubset(frame.columns):
        return np.full((len(frame), len(odds_cols)), np.nan), np.zeros(len(frame), dtype=bool)
    probs, mask = [], []
    for prices in frame[odds_cols].itertuples(index=False):
        m = devig(prices)
        mask.append(m is not None)
        probs.append(m if m is not None else np.full(len(odds_cols), np.nan))
    return np.vstack(probs) if probs else np.empty((0, len(odds_cols))), np.asarray(mask, dtype=bool)


def _dc_1x2(X: pd.DataFrame) -> np.ndarray:
    dc = X[["dc_prob_home", "dc_prob_draw", "dc_prob_away"]].to_numpy(dtype=float)
    return dc / dc.sum(axis=1, keepdims=True)


def holdout_market_report(X_test: pd.DataFrame, y_test: pd.DataFrame, probs_1x2: np.ndarray,
                          probs_over25: np.ndarray, w_ml_1x2: float = 0.70, w_ml_ou: float = 0.65) -> Dict[str, Any]:
    """Score the deployed probabilities (ML/Dixon-Coles blend) against Bet365/average prices on the holdout."""
    report: Dict[str, Any] = {}
    blend_1x2 = blend(probs_1x2, _dc_1x2(X_test), w_ml_1x2)
    mkt, mask = market_probabilities(y_test, ["odds_home", "odds_draw", "odds_away"])
    y_1x2 = y_test["target_1x2"].to_numpy(dtype=int)
    if mask.any():
        report["holdout_vs_market_1x2"] = compare_to_market(blend_1x2[mask], mkt[mask], y_1x2[mask])
        report["holdout_vs_market_1x2_ml_only"] = compare_to_market(probs_1x2[mask], mkt[mask], y_1x2[mask])
    blend_ou = blend(probs_over25, X_test["dc_prob_over25"].to_numpy(dtype=float), w_ml_ou)
    mkt_ou, mask_ou = market_probabilities(y_test, ["odds_over25", "odds_under25"])
    if mask_ou.any():
        report["holdout_vs_market_over25"] = compare_to_market(
            blend_ou[mask_ou], mkt_ou[mask_ou][:, 0], y_test["target_over25"].to_numpy(dtype=int)[mask_ou])
    return report


ODDS_1X2 = ["odds_home", "odds_draw", "odds_away"]
ODDS_OU = ["odds_over25", "odds_under25"]
MIN_ROWS_FOR_MARKET_WEIGHT = 50


def fit_market_weights(final_1x2: np.ndarray, final_ou: np.ndarray, y_val: pd.DataFrame) -> Dict[str, float]:
    """How much to trust the model versus the vig-free price, fitted on the validation window.

    BTTS has no historical prices in football-data.co.uk, so it reuses the Over/Under weight.
    """
    weights = {"1x2": DEFAULT_MARKET_MODEL_WEIGHT, "over25": DEFAULT_MARKET_MODEL_WEIGHT}
    mkt, mask = market_probabilities(y_val, ODDS_1X2)
    if mask.sum() >= MIN_ROWS_FOR_MARKET_WEIGHT:
        weights["1x2"] = fit_market_blend_weight(final_1x2[mask], mkt[mask],
                                                 y_val["target_1x2"].to_numpy(dtype=int)[mask])["weight"]
    mkt_ou, mask_ou = market_probabilities(y_val, ODDS_OU)
    if mask_ou.sum() >= MIN_ROWS_FOR_MARKET_WEIGHT:
        weights["over25"] = fit_market_blend_weight(final_ou[mask_ou], mkt_ou[mask_ou][:, 0],
                                                    y_val["target_over25"].to_numpy(dtype=int)[mask_ou])["weight"]
    weights["btts"] = weights["over25"]
    return weights


def market_aware_report(final_1x2: np.ndarray, final_ou: np.ndarray, y_test: pd.DataFrame,
                        weights: Dict[str, float]) -> Dict[str, Any]:
    """Test-window quality of the market-blended probabilities and a flat-stake backtest of the
    value-bet rule, both as it used to run (raw model, no EV cap) and as it runs now."""
    report: Dict[str, Any] = {}
    mkt, mask = market_probabilities(y_test, ODDS_1X2)
    if mask.any():
        y = y_test["target_1x2"].to_numpy(dtype=int)[mask]
        odds = y_test.loc[mask, ODDS_1X2].to_numpy(dtype=float)
        blended = blend(final_1x2[mask], mkt[mask], weights["1x2"])
        report["holdout_final_vs_market_1x2"] = compare_to_market(blended, mkt[mask], y)
        rules = dict(min_ev=MIN_VALUE_THRESHOLD, max_odds=MAX_VALUE_ODDS, min_prob=MIN_VALUE_PROB)
        report["backtest_1x2_model_only"] = backtest_value_bets(final_1x2[mask], odds, y, **rules)
        report["backtest_1x2_market_aware"] = backtest_value_bets(blended, odds, y, max_ev=MAX_CREDIBLE_EV, **rules)
    mkt_ou, mask_ou = market_probabilities(y_test, ODDS_OU)
    if mask_ou.any():
        y = 1 - y_test["target_over25"].to_numpy(dtype=int)[mask_ou]  # selection index: 0 = over, 1 = under
        odds = y_test.loc[mask_ou, ODDS_OU].to_numpy(dtype=float)
        raw = np.column_stack([final_ou[mask_ou], 1.0 - final_ou[mask_ou]])
        blended_over = blend(final_ou[mask_ou], mkt_ou[mask_ou][:, 0], weights["over25"])
        blended = np.column_stack([blended_over, 1.0 - blended_over])
        rules = dict(min_ev=MIN_VALUE_THRESHOLD, max_odds=MAX_VALUE_ODDS, min_prob=MIN_VALUE_PROB)
        report["backtest_over25_model_only"] = backtest_value_bets(raw, odds, y, **rules)
        report["backtest_over25_market_aware"] = backtest_value_bets(blended, odds, y, max_ev=MAX_CREDIBLE_EV, **rules)
    return report


def heuristic_props_report(X_test: pd.DataFrame, y_test: pd.DataFrame, y_train: pd.DataFrame) -> Dict[str, Any]:
    """Holdout log loss of the corners/cards heuristics vs simply predicting the training base rate."""
    report = {}
    for name, prob_col, target_col in (("corners_o95", "prob_corners_o95_poisson", "target_corners_over95"),
                                       ("cards_o35", "prob_cards_o35_poisson", "target_cards_over35")):
        if target_col not in y_test.columns or prob_col not in X_test.columns:
            continue
        mask = y_test[target_col].notna().to_numpy()
        train_targets = y_train[target_col].dropna()
        if mask.sum() < 30 or train_targets.empty:
            continue
        y_true = y_test.loc[mask, target_col].to_numpy(dtype=int)
        heuristic = X_test.loc[mask, prob_col].to_numpy(dtype=float)
        base = np.full(len(y_true), float(train_targets.mean()))
        h_ll, b_ll = log_loss(heuristic, y_true), log_loss(base, y_true)
        report[f"heuristic_{name}"] = {"n": int(mask.sum()), "log_loss": round(h_ll, 4),
                                       "base_rate_log_loss": round(b_ll, 4), "skill": round(h_ll - b_ll, 4)}
    return report


def train_league_models(X: pd.DataFrame, y: pd.DataFrame, league_key: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Train calibrated 1X2, Over/Under 2.5 and BTTS models; return (deployed models, holdout metrics)."""
    if X.empty or len(X) < MIN_TRAINING_ROWS:
        logger.warning(f"Insufficient training samples for {league_key} ({len(X)} rows)")
        return {}, {}

    n = len(X)
    i_val, i_test = int(n * TRAIN_FRACTION), int(n * (TRAIN_FRACTION + VALIDATION_FRACTION))
    X_tr, y_tr = X.iloc[:i_val], y.iloc[:i_val]
    X_va, y_va = X.iloc[i_val:i_test], y.iloc[i_val:i_test]
    X_te, y_te = X.iloc[i_test:], y.iloc[i_test:]

    logger.info(f"[{league_key}] Fitting on {len(X_tr)} matches (validation {len(X_va)}, test {len(X_te)})...")
    fitted = fit_outcome_models(X_tr, y_tr)

    def _predict(models, frame):
        return (models["model_1x2"].predict_proba(frame),
                models["model_over25"].predict_proba(frame)[:, 1],
                models["model_btts"].predict_proba(frame)[:, 1])

    # Blend weights (ML vs Dixon-Coles) chosen on the validation window only.
    p1x2_va, pou_va, pbtts_va = _predict(fitted, X_va)
    w_1x2 = fit_market_blend_weight(p1x2_va, _dc_1x2(X_va), y_va["target_1x2"].to_numpy(dtype=int))["weight"]
    w_ou = fit_market_blend_weight(pou_va, X_va["dc_prob_over25"].to_numpy(dtype=float),
                                   y_va["target_over25"].to_numpy(dtype=int))["weight"]
    w_btts = fit_market_blend_weight(pbtts_va, X_va["dc_prob_btts"].to_numpy(dtype=float),
                                     y_va["target_btts"].to_numpy(dtype=int))["weight"]

    # Model-vs-market weights, also from the validation window
    market_weights = fit_market_weights(
        blend(p1x2_va, _dc_1x2(X_va), w_1x2),
        blend(pou_va, X_va["dc_prob_over25"].to_numpy(dtype=float), w_ou),
        y_va,
    )

    # Everything reported below comes from the untouched test window.
    p1x2_te, pou_te, pbtts_te = _predict(fitted, X_te)
    final_1x2 = blend(p1x2_te, _dc_1x2(X_te), w_1x2)
    final_ou = blend(pou_te, X_te["dc_prob_over25"].to_numpy(dtype=float), w_ou)
    final_btts = blend(pbtts_te, X_te["dc_prob_btts"].to_numpy(dtype=float), w_btts)
    y1x2_te = y_te["target_1x2"].to_numpy(dtype=int)
    you_te = y_te["target_over25"].to_numpy(dtype=int)
    ybtts_te = y_te["target_btts"].to_numpy(dtype=int)

    onehot = np.eye(3)[y1x2_te]
    metrics: Dict[str, Any] = {
        "schema_version": FEATURE_SCHEMA_VERSION,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_end": str(pd.Timestamp(y["Date"].max()).date()) if "Date" in y else None,
        "n_train": len(X_tr),
        "n_validation": len(X_va),
        "n_test": len(X_te),
        "blend_weights": {"ml_1x2": w_1x2, "ml_over25": w_ou, "ml_btts": w_btts},
        "market_weights": market_weights,
        "acc_1x2": float(np.mean(np.argmax(final_1x2, axis=1) == y1x2_te)),
        "log_loss_1x2": round(log_loss(final_1x2, y1x2_te), 4),
        "brier_1x2": round(float(np.mean(np.sum((final_1x2 - onehot) ** 2, axis=1))), 4),
        "acc_over25": float(np.mean((final_ou >= 0.5) == you_te)),
        "log_loss_over25": round(log_loss(final_ou, you_te), 4),
        "acc_btts": float(np.mean((final_btts >= 0.5) == ybtts_te)),
        "log_loss_btts": round(log_loss(final_btts, ybtts_te), 4),
        **holdout_market_report(X_te, y_te, p1x2_te, pou_te, w_ml_1x2=w_1x2, w_ml_ou=w_ou),
        **heuristic_props_report(X_te, y_te, y_tr),
        **market_aware_report(final_1x2, final_ou, y_te, market_weights),
    }

    # Deployed models see every match, including the most recent seasons.
    models = fit_outcome_models(X, y)
    metrics["feature_importances"] = dict(zip(X.columns, models["base_1x2"].feature_importances_.tolist()))

    vs_mkt = metrics.get("holdout_vs_market_1x2", {})
    logger.info(
        f"[{league_key}] Test 1X2 acc {metrics['acc_1x2']*100:.1f}% | log loss {metrics['log_loss_1x2']:.4f}"
        + (f" vs market {vs_mkt['market_log_loss']:.4f} (n={vs_mkt['n']})" if vs_mkt else "")
        + f" | blend ML weight {w_1x2:.2f}"
    )
    return models, metrics


def save_trained_bundle(
    pipeline: FootballFeaturePipeline,
    models: Dict[str, Any],
    metrics: Dict[str, Any],
    league_key: str
):
    """Save pipeline, models, and metrics to disk."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    bundle_path = MODELS_DIR / f"{league_key}_bundle.joblib"
    bundle = {
        "league_key": league_key,
        "pipeline": pipeline,
        "models": models,
        "metrics": metrics,
    }
    joblib.dump(bundle, bundle_path)
    logger.info(f"Saved model bundle for {league_key} to {bundle_path.name}")
    record_metrics(league_key, metrics)
    return bundle_path


def record_metrics(league_key: str, metrics: Dict[str, Any]) -> None:
    """Keep a small JSON copy of each league's holdout metrics for reports (no unpickling needed)."""
    all_metrics = read_json(METRICS_FILE, default={}) or {}
    all_metrics[league_key] = {k: v for k, v in metrics.items() if k != "feature_importances"}
    write_json_atomic(METRICS_FILE, all_metrics)


def load_trained_bundle(league_key: str) -> Optional[Dict[str, Any]]:
    """Load model bundle from disk."""
    bundle_path = MODELS_DIR / f"{league_key}_bundle.joblib"
    if bundle_path.exists():
        try:
            return joblib.load(bundle_path)
        except Exception as e:
            logger.error(f"Error loading bundle for {league_key}: {e}")
    return None


def retrain_league(league_key: str, cleaned_df: pd.DataFrame, gate: bool = True) -> Dict[str, Any]:
    """Rebuild features, train, and save a league bundle, keeping the deployed models if the candidate is worse.

    The pipeline state (ratings, form, Dixon-Coles fit) is always refreshed with the latest matches;
    only the classifiers are subject to the promotion gate.
    """
    from sports_common.evaluation import should_promote

    pipeline = FootballFeaturePipeline(league_key=league_key)
    X, y = pipeline.process_historical_matches(cleaned_df)
    models, metrics = train_league_models(X, y, league_key=league_key)
    if not models:
        return {"league": league_key, "status": "skipped", "reason": "not enough data"}

    current = load_trained_bundle(league_key) if gate else None
    promote, reason = should_promote(metrics, (current or {}).get("metrics"), "holdout_vs_market_1x2",
                                     FEATURE_SCHEMA_VERSION, UNINFORMED_LOG_LOSS_1X2)
    if not gate or promote or not current or not current.get("models"):
        save_trained_bundle(pipeline, models, metrics, league_key)
        return {"league": league_key, "status": "promoted", "reason": reason if gate else "gate disabled"}

    kept = dict(current["metrics"])
    kept["rejected_candidate"] = {k: v for k, v in metrics.items() if k != "feature_importances"}
    save_trained_bundle(pipeline, current["models"], kept, league_key)
    logger.warning(f"[{league_key}] Kept the deployed models: {reason}")
    return {"league": league_key, "status": "kept_current", "reason": reason}
