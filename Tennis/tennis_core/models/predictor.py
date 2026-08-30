"""Matchup outcome prediction engine and inference wrapper."""
import logging
import pickle
from pathlib import Path
from typing import Dict, Optional
import pandas as pd
import numpy as np

from tennis_core.config import ATP_MODEL_PATH, WTA_MODEL_PATH, MODELS_DIR
from tennis_core.features.builder import FEATURE_COLUMNS, TennisFeaturePipeline
from tennis_core.betting.value import analyze_betting_value
from tennis_core.models.explain import explain_matchup_prediction
from tennis_core.models.sets_games import calculate_sets_and_games_probabilities
from tennis_core.utils.helpers import normalize_player_name, normalize_surface

logger = logging.getLogger(__name__)


class TennisPredictor:
    """Predictor engine that loads models and pipelines for ATP/WTA match inference."""

    def __init__(self):
        self.models = {}
        self.pipelines = {}
        self._load_artifacts()

    def _load_artifacts(self):
        """Load trained models and feature pipelines."""
        try:
            from compat import setup_legacy_compat
            setup_legacy_compat()
        except Exception:
            pass

        for circuit in ["atp", "wta"]:
            model_path = ATP_MODEL_PATH if circuit == "atp" else WTA_MODEL_PATH
            pipeline_path = MODELS_DIR / f"{circuit}_pipeline.pkl"
            
            if model_path.exists() and pipeline_path.exists():
                try:
                    with open(model_path, "rb") as f:
                        self.models[circuit] = pickle.load(f)
                    with open(pipeline_path, "rb") as f:
                        self.pipelines[circuit] = pickle.load(f)
                    logger.info(f"Loaded trained {circuit.upper()} model and pipeline.")
                except Exception as e:
                    logger.warning(f"Failed to load artifacts for {circuit}: {e}")
            else:
                logger.info(f"No trained model found for {circuit.upper()} yet at {model_path}.")

    def predict_match(
        self,
        circuit: str,
        p1_name: str,
        p2_name: str,
        surface: str,
        p1_odds: Optional[float] = None,
        p2_odds: Optional[float] = None,
        p1_rank: Optional[float] = None,
        p2_rank: Optional[float] = None,
        match_date: Optional[pd.Timestamp] = None,
        best_of: Optional[int] = 3,
        bankroll: float = 1000.0,
    ) -> Dict:
        """
        Generate full matchup prediction, betting value analysis, and explanation.
        """
        circuit = circuit.lower()
        pipeline: Optional[TennisFeaturePipeline] = self.pipelines.get(circuit)
        model = self.models.get(circuit)
        
        p1 = normalize_player_name(p1_name)
        p2 = normalize_player_name(p2_name)
        surf = normalize_surface(surface)

        # 1. Compute features
        if pipeline:
            data_bundle = pipeline.build_inference_features(
                p1_name=p1, p2_name=p2, surface=surf, match_date=match_date, p1_rank=p1_rank, p2_rank=p2_rank
            )
            features_dict = data_bundle["features"]
            context = data_bundle["context"]
        else:
            # Fallback baseline context
            features_dict = {"effective_surface_elo_diff": 0.0, "elo_diff": 0.0}
            context = {
                "p1_name": p1, "p2_name": p2, "surface": surf,
                "p1_elo": 1500.0, "p2_elo": 1500.0,
                "p1_surface_elo": 1500.0, "p2_surface_elo": 1500.0,
                "p1_eff_surface_elo": 1500.0, "p2_eff_surface_elo": 1500.0,
                "p1_rank": p1_rank or "N/A", "p2_rank": p2_rank or "N/A",
                "p1_career_high": "N/A", "p2_career_high": "N/A",
                "p1_form_5": 50.0, "p2_form_5": 50.0,
                "p1_surface_form": 50.0, "p2_surface_form": 50.0,
                "h2h_p1_wins": 0, "h2h_p2_wins": 0, "h2h_total": 0,
            }

        # 2. Probability Estimation
        if model is not None and pipeline is not None:
            feature_vector = pd.DataFrame([features_dict])[FEATURE_COLUMNS].fillna(0.0)
            proba = model.predict_proba(feature_vector)[0]
            # proba[1] is P(P1 wins)
            p1_prob = float(proba[1])
            p2_prob = float(proba[0])
        else:
            # Logistic Elo Fallback
            eff_elo_diff = features_dict.get("effective_surface_elo_diff", 0.0)
            p1_prob = 1.0 / (1.0 + 10.0 ** (-eff_elo_diff / 400.0))
            p2_prob = 1.0 - p1_prob

        # Ensure sensible bounds
        p1_prob = max(0.02, min(0.98, p1_prob))
        p2_prob = 1.0 - p1_prob

        # 3. Betting Value Analysis
        betting_analysis = analyze_betting_value(
            p1_name=p1,
            p2_name=p2,
            p1_model_prob=p1_prob,
            p2_model_prob=p2_prob,
            p1_odds=p1_odds,
            p2_odds=p2_odds,
            bankroll=bankroll
        )

        # 4. Sets and Total Games Analytics
        h1_proj = context.get("projected_p1_hold_rate") if isinstance(context.get("projected_p1_hold_rate"), (int, float)) else None
        h2_proj = context.get("projected_p2_hold_rate") if isinstance(context.get("projected_p2_hold_rate"), (int, float)) else None
        
        sets_games = calculate_sets_and_games_probabilities(
            p1_match_prob=p1_prob,
            circuit=circuit,
            surface=surf,
            best_of=best_of or 3,
            p1_name=p1,
            p2_name=p2,
            p1_hold_rate=h1_proj,
            p2_hold_rate=h2_proj,
        )

        # 5. Explainability Factors
        factors = explain_matchup_prediction(context, p1_prob, p2_prob)

        return {
            "circuit": circuit.upper(),
            "p1_name": p1,
            "p2_name": p2,
            "surface": surf,
            "p1_prob": round(p1_prob * 100, 1),
            "p2_prob": round(p2_prob * 100, 1),
            "predicted_winner": p1 if p1_prob >= p2_prob else p2,
            "confidence": round(max(p1_prob, p2_prob) * 100, 1),
            "context": context,
            "betting": betting_analysis,
            "sets_games": sets_games,
            "factors": factors,
        }

