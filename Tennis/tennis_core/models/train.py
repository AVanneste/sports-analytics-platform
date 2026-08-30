"""Machine Learning Model Training, Validation, and Calibration."""
import json
import logging
import pickle
from pathlib import Path
from typing import Dict, Tuple
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss, roc_auc_score

from tennis_core.config import ATP_MODEL_PATH, WTA_MODEL_PATH, METRICS_PATH, MODELS_DIR
from tennis_core.features.builder import FEATURE_COLUMNS, TennisFeaturePipeline

logger = logging.getLogger(__name__)


def train_tennis_model(
    X: pd.DataFrame,
    y: pd.Series,
    circuit: str,
    test_size_ratio: float = 0.20
) -> Tuple[CalibratedClassifierCV, Dict]:
    """
    Train a LightGBM Classifier with probability calibration using chronological time split.
    """
    if X.empty or len(X) < 100:
        raise ValueError(f"Insufficient training data for {circuit}: {len(X)} samples")

    feature_cols = [c for c in FEATURE_COLUMNS if c in X.columns]
    X_features = X[feature_cols].copy().fillna(0.0)

    # Time-based train/test split to avoid lookahead bias
    split_idx = int(len(X_features) * (1.0 - test_size_ratio))
    X_train, X_test = X_features.iloc[:split_idx], X_features.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    logger.info(f"Training {circuit.upper()} model: {len(X_train)} train samples, {len(X_test)} test samples")

    # Base LightGBM model
    base_lgb = lgb.LGBMClassifier(
        n_estimators=250,
        learning_rate=0.03,
        num_leaves=31,
        max_depth=6,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_samples=20,
        random_state=42,
        verbosity=-1
    )

    # Calibrated Classifier to ensure accurate, unskewed betting win probabilities
    calibrated_model = CalibratedClassifierCV(
        estimator=base_lgb,
        method="sigmoid",
        cv=3
    )
    
    calibrated_model.fit(X_train, y_train)

    # Evaluation on Out-Of-Time Test Set
    y_pred_proba = calibrated_model.predict_proba(X_test)[:, 1]
    y_pred_class = (y_pred_proba >= 0.5).astype(int)

    acc = float(accuracy_score(y_test, y_pred_class))
    auc = float(roc_auc_score(y_test, y_pred_proba))
    ll = float(log_loss(y_test, y_pred_proba))
    brier = float(brier_score_loss(y_test, y_pred_proba))

    # Train base model on full data for feature importance extraction
    base_lgb.fit(X_features, y)
    importances = dict(zip(feature_cols, [float(v) for v in base_lgb.feature_importances_]))
    # Sort feature importances
    sorted_importances = dict(sorted(importances.items(), key=lambda item: item[1], reverse=True))

    metrics = {
        "circuit": circuit.upper(),
        "total_samples": len(X),
        "test_samples": len(X_test),
        "accuracy": round(acc * 100, 2),
        "roc_auc": round(auc, 4),
        "log_loss": round(ll, 4),
        "brier_score": round(brier, 4),
        "feature_importances": sorted_importances,
    }

    logger.info(f"[{circuit.upper()} Evaluation] Accuracy: {metrics['accuracy']}%, AUC: {metrics['roc_auc']}, Brier: {metrics['brier_score']}")
    return calibrated_model, metrics


def save_trained_pipeline(pipeline: TennisFeaturePipeline, model: CalibratedClassifierCV, metrics: Dict, circuit: str):
    """Save the model and feature pipeline state to disk."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = ATP_MODEL_PATH if circuit.lower() == "atp" else WTA_MODEL_PATH
    pipeline_path = MODELS_DIR / f"{circuit.lower()}_pipeline.pkl"
    
    with open(model_path, "wb") as f:
        pickle.dump(model, f)
        
    with open(pipeline_path, "wb") as f:
        pickle.dump(pipeline, f)
        
    # Save/update metrics JSON
    all_metrics = {}
    if METRICS_PATH.exists():
        try:
            with open(METRICS_PATH, "r") as f:
                all_metrics = json.load(f)
        except Exception:
            all_metrics = {}
            
    all_metrics[circuit.lower()] = metrics
    with open(METRICS_PATH, "w") as f:
        json.dump(all_metrics, f, indent=2)
        
    logger.info(f"Saved {circuit.upper()} model and pipeline artifacts to {MODELS_DIR}")

