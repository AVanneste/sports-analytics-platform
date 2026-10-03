"""LightGBM + sigmoid calibration estimators shared by the domestic and international trainers."""
from typing import Any, Dict

import lightgbm as lgb
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import TimeSeriesSplit


# One thread: on a few thousand rows it is as fast as more threads, it is deterministic, and the
# default (one thread per physical core, ignoring OMP_NUM_THREADS) oversubscribes parallel backtests.
LGBM_THREADS = 1


def multiclass_lgbm() -> lgb.LGBMClassifier:
    return lgb.LGBMClassifier(
        n_estimators=150, learning_rate=0.03, num_leaves=15, max_depth=5, min_child_samples=20,
        subsample=0.8, colsample_bytree=0.8, random_state=42, objective="multiclass", num_class=3,
        verbosity=-1, n_jobs=LGBM_THREADS,
    )


def binary_lgbm() -> lgb.LGBMClassifier:
    return lgb.LGBMClassifier(
        n_estimators=120, learning_rate=0.03, num_leaves=15, max_depth=4, min_child_samples=20,
        subsample=0.8, colsample_bytree=0.8, random_state=42, objective="binary", verbosity=-1,
        n_jobs=LGBM_THREADS,
    )


def calibrated(base: lgb.LGBMClassifier, n_splits: int = 5) -> CalibratedClassifierCV:
    """Sigmoid calibration on chronological folds (never calibrates on the past using the future)."""
    return CalibratedClassifierCV(estimator=base, method="sigmoid", cv=TimeSeriesSplit(n_splits=n_splits))


def fit_outcome_models(X: pd.DataFrame, y: pd.DataFrame) -> Dict[str, Any]:
    """Calibrated 1X2, Over/Under 2.5 and BTTS classifiers plus an uncalibrated 1X2 model for importances."""
    return {
        "model_1x2": calibrated(multiclass_lgbm()).fit(X, y["target_1x2"]),
        "model_over25": calibrated(binary_lgbm()).fit(X, y["target_over25"]),
        "model_btts": calibrated(binary_lgbm()).fit(X, y["target_btts"]),
        "base_1x2": multiclass_lgbm().fit(X, y["target_1x2"]),
    }
