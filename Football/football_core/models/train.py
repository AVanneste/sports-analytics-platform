"""Model Training & Calibration Pipeline for Football Match, Corners, and Cards Predictions."""
import logging
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, Tuple, Any
from sklearn.metrics import accuracy_score, log_loss, roc_auc_score
from sklearn.calibration import CalibratedClassifierCV
import lightgbm as lgb

from football_core.config import MODELS_DIR
from football_core.features.builder import FootballFeaturePipeline

logger = logging.getLogger(__name__)


def train_league_models(X: pd.DataFrame, y: pd.DataFrame, league_key: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Train and calibrate models for 1X2, Over/Under 2.5, BTTS, Corners, and Cards.
    """
    if X.empty or len(X) < 100:
        logger.warning(f"Insufficient training samples for {league_key} ({len(X)} rows)")
        return {}, {}

    n_samples = len(X)
    train_end = int(n_samples * 0.80)

    X_train, y_train = X.iloc[:train_end], y.iloc[:train_end]
    X_test, y_test = X.iloc[train_end:], y.iloc[train_end:]

    # 1. Multi-class 1X2 Model
    logger.info(f"[{league_key}] Training 1X2 Multi-class Classifier...")
    model_1x2_base = lgb.LGBMClassifier(
        n_estimators=150,
        learning_rate=0.03,
        num_leaves=15,
        max_depth=5,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        objective="multiclass",
        num_class=3,
        verbosity=-1,
    )
    cal_1x2 = CalibratedClassifierCV(estimator=model_1x2_base, method="sigmoid", cv=5)
    cal_1x2.fit(X_train, y_train["target_1x2"])
    model_1x2_base.fit(X_train, y_train["target_1x2"])

    # 2. Over / Under 2.5 Goals Model
    logger.info(f"[{league_key}] Training Over/Under 2.5 Classifier...")
    model_ou_base = lgb.LGBMClassifier(
        n_estimators=120,
        learning_rate=0.03,
        num_leaves=15,
        max_depth=4,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        objective="binary",
        verbosity=-1,
    )
    cal_ou = CalibratedClassifierCV(estimator=model_ou_base, method="sigmoid", cv=5)
    cal_ou.fit(X_train, y_train["target_over25"])

    # 3. Both Teams To Score (BTTS) Model
    logger.info(f"[{league_key}] Training BTTS Classifier...")
    model_btts_base = lgb.LGBMClassifier(
        n_estimators=120,
        learning_rate=0.03,
        num_leaves=15,
        max_depth=4,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        objective="binary",
        verbosity=-1,
    )
    cal_btts = CalibratedClassifierCV(estimator=model_btts_base, method="sigmoid", cv=5)
    cal_btts.fit(X_train, y_train["target_btts"])

    # 4. Over / Under 9.5 Corners Model
    logger.info(f"[{league_key}] Training Over/Under 9.5 Corners Classifier...")
    model_corners_base = lgb.LGBMClassifier(
        n_estimators=100,
        learning_rate=0.03,
        num_leaves=12,
        max_depth=4,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        objective="binary",
        verbosity=-1,
    )
    cal_corners = CalibratedClassifierCV(estimator=model_corners_base, method="sigmoid", cv=5)
    cal_corners.fit(X_train, y_train["target_corners_over95"])

    # 5. Over / Under 3.5 Cards Model (with Referee features)
    logger.info(f"[{league_key}] Training Over/Under 3.5 Cards Classifier...")
    model_cards35_base = lgb.LGBMClassifier(
        n_estimators=100,
        learning_rate=0.03,
        num_leaves=12,
        max_depth=4,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        objective="binary",
        verbosity=-1,
    )
    cal_cards35 = CalibratedClassifierCV(estimator=model_cards35_base, method="sigmoid", cv=5)
    cal_cards35.fit(X_train, y_train["target_cards_over35"])

    # 6. Over / Under 4.5 Cards Model
    logger.info(f"[{league_key}] Training Over/Under 4.5 Cards Classifier...")
    model_cards45_base = lgb.LGBMClassifier(
        n_estimators=100,
        learning_rate=0.03,
        num_leaves=12,
        max_depth=4,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        objective="binary",
        verbosity=-1,
    )
    cal_cards45 = CalibratedClassifierCV(estimator=model_cards45_base, method="sigmoid", cv=5)
    cal_cards45.fit(X_train, y_train["target_cards_over45"])

    # Out-of-Sample Evaluations
    probs_1x2 = cal_1x2.predict_proba(X_test)
    preds_1x2 = np.argmax(probs_1x2, axis=1)
    acc_1x2 = accuracy_score(y_test["target_1x2"], preds_1x2)
    loss_1x2 = log_loss(y_test["target_1x2"], probs_1x2)

    probs_ou = cal_ou.predict_proba(X_test)[:, 1]
    acc_ou = accuracy_score(y_test["target_over25"], (probs_ou >= 0.5).astype(int))

    probs_btts = cal_btts.predict_proba(X_test)[:, 1]
    acc_btts = accuracy_score(y_test["target_btts"], (probs_btts >= 0.5).astype(int))

    probs_corners = cal_corners.predict_proba(X_test)[:, 1]
    acc_corners = accuracy_score(y_test["target_corners_over95"], (probs_corners >= 0.5).astype(int))

    probs_cards35 = cal_cards35.predict_proba(X_test)[:, 1]
    acc_cards35 = accuracy_score(y_test["target_cards_over35"], (probs_cards35 >= 0.5).astype(int))

    probs_cards45 = cal_cards45.predict_proba(X_test)[:, 1]
    acc_cards45 = accuracy_score(y_test["target_cards_over45"], (probs_cards45 >= 0.5).astype(int))

    y_test_onehot = pd.get_dummies(y_test["target_1x2"]).values
    brier_1x2 = float(np.mean(np.sum((probs_1x2 - y_test_onehot) ** 2, axis=1)))

    metrics = {
        "n_train": len(X_train),
        "n_test": len(X_test),
        "acc_1x2": float(acc_1x2),
        "log_loss_1x2": float(loss_1x2),
        "brier_1x2": float(brier_1x2),
        "acc_over25": float(acc_ou),
        "acc_btts": float(acc_btts),
        "acc_corners_o95": float(acc_corners),
        "acc_cards_o35": float(acc_cards35),
        "acc_cards_o45": float(acc_cards45),
        "feature_importances": dict(zip(X.columns, model_1x2_base.feature_importances_.tolist())),
    }

    models = {
        "model_1x2": cal_1x2,
        "model_over25": cal_ou,
        "model_btts": cal_btts,
        "model_corners_o95": cal_corners,
        "model_cards_o35": cal_cards35,
        "model_cards_o45": cal_cards45,
        "base_1x2": model_1x2_base,
    }

    logger.info(f"[{league_key}] Results -> 1X2: {acc_1x2*100:.1f}% | O/U 2.5: {acc_ou*100:.1f}% | Corners >9.5: {acc_corners*100:.1f}% | Cards >3.5: {acc_cards35*100:.1f}%")

    return models, metrics


def save_trained_bundle(
    pipeline: FootballFeaturePipeline,
    models: Dict[str, Any],
    metrics: Dict[str, Any],
    league_key: str
) -> Path:
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
    return bundle_path


def load_trained_bundle(league_key: str) -> Optional[Dict[str, Any]]:
    """Load model bundle from disk."""
    bundle_path = MODELS_DIR / f"{league_key}_bundle.joblib"
    if bundle_path.exists():
        try:
            return joblib.load(bundle_path)
        except Exception as e:
            logger.error(f"Error loading bundle for {league_key}: {e}")
    return None
