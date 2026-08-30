"""Command-Line Pipeline Runner: Data Ingestion, Model Training, Predictions, and Results Reconciliation."""
import argparse
import logging
import sys
from pathlib import Path
import pandas as pd

from tennis_core.config import CIRCUITS, START_YEAR, END_YEAR
from tennis_core.data.fetcher import fetch_all_data
from tennis_core.data.preprocessor import clean_match_data, load_raw_matches
from tennis_core.features.builder import TennisFeaturePipeline
from tennis_core.models.train import train_tennis_model, save_trained_pipeline
from tennis_core.models.predictor import TennisPredictor
from tennis_core.data.scraper import load_upcoming_matches
from tennis_core.betting.tracker import PredictionTracker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def run_data_fetch(force: bool = False):
    """Step 1: Download ATP & WTA historical datasets."""
    logger.info(">>> STEP 1: Fetching historical ATP and WTA data from repository...")
    fetch_all_data(force=force)


def run_training():
    """Step 2: Clean data, compute dynamic features (surface Elo, form, H2H), train & calibrate LightGBM."""
    logger.info(">>> STEP 2: Building features and training models for ATP & WTA...")
    
    for circuit in CIRCUITS:
        logger.info(f"\n--- Training {circuit.upper()} Prediction Pipeline ---")
        raw_df = load_raw_matches(circuit)
        if raw_df.empty:
            logger.warning(f"No raw match data found for {circuit.upper()}. Run with --fetch first!")
            continue
            
        cleaned_df = clean_match_data(raw_df, circuit=circuit)
        
        # Build features chronologically
        pipeline = TennisFeaturePipeline(circuit=circuit)
        X, y = pipeline.process_historical_matches(cleaned_df)
        
        if X.empty:
            logger.warning(f"Could not build features for {circuit.upper()}")
            continue
            
        # Train and calibrate model
        model, metrics = train_tennis_model(X, y, circuit=circuit)
        
        # Save model and feature state
        save_trained_pipeline(pipeline, model, metrics, circuit=circuit)
        
    logger.info("\n>>> Model training and artifact saving complete!")


def run_predictions():
    """Step 3: Generate predictions for upcoming week's matches and log to tracker."""
    logger.info(">>> STEP 3: Predicting outcomes for upcoming week's matches...")
    predictor = TennisPredictor()
    tracker = PredictionTracker()
    
    upcoming = load_upcoming_matches()
    if not upcoming:
        from tennis_core.data.scraper import fetch_live_upcoming_fixtures
        upcoming = fetch_live_upcoming_fixtures()
        
    if not upcoming:
        logger.info("No upcoming fixtures found.")
        return
        
    logger.info(f"Loaded {len(upcoming)} upcoming matches.")
    
    for match in upcoming:
        pred = predictor.predict_match(
            circuit=match.get("circuit", "ATP"),
            p1_name=match["p1_name"],
            p2_name=match["p2_name"],
            surface=match.get("surface", "Hard"),
            p1_odds=match.get("p1_odds"),
            p2_odds=match.get("p2_odds"),
            p1_rank=match.get("p1_rank"),
            p2_rank=match.get("p2_rank"),
        )
        
        # Archive prediction
        tracker_payload = {
            "match_id": match.get("match_id"),
            "circuit": match.get("circuit", "ATP"),
            "tourney_name": match.get("tourney_name", "Upcoming Tourney"),
            "surface": match.get("surface", "Hard"),
            "date": match.get("date"),
            "round": match.get("round", "Main Draw"),
            "p1_name": pred["p1_name"],
            "p2_name": pred["p2_name"],
            "p1_prob": pred["p1_prob"],
            "p2_prob": pred["p2_prob"],
            "p1_odds": pred["betting"]["p1_odds"],
            "p2_odds": pred["betting"]["p2_odds"],
            "recommended_pick": pred["betting"]["recommended_pick"],
            "best_ev": pred["betting"]["best_ev"],
            "best_edge": pred["betting"]["best_edge"],
            "best_stake": pred["betting"]["best_stake"],
            "best_odds": pred["betting"]["best_odds"],
        }
        tracker.log_prediction(tracker_payload)
        
        rec_str = f" ⭐ Value Bet: {pred['betting']['recommended_pick']} (EV: +{pred['betting']['best_ev']}%)" if pred['betting']['has_value'] else ""
        logger.info(
            f"[{match.get('circuit')}] {pred['p1_name']} ({pred['p1_prob']}%) vs {pred['p2_name']} ({pred['p2_prob']}%) "
            f"on {pred['surface']} | Favored: {pred['predicted_winner']}{rec_str}"
        )


def run_reconcile():
    """Step 4: Reconcile predictions against completed results."""
    logger.info(">>> STEP 4: Reconciling predictions against latest match results...")
    tracker = PredictionTracker()
    
    total_reconciled = 0
    for circuit in CIRCUITS:
        raw_df = load_raw_matches(circuit)
        if not raw_df.empty:
            cleaned = clean_match_data(raw_df, circuit)
            reconciled = tracker.auto_reconcile(cleaned)
            total_reconciled += reconciled
            
    summary = tracker.get_performance_summary()
    logger.info(f"Reconciled {total_reconciled} predictions. Total Graded: {summary['total_graded']}, Model Accuracy: {summary['accuracy']}%, ROI: {summary['roi']}%")


def main():
    parser = argparse.ArgumentParser(description="Tennis Match Prediction & Value Engine Pipeline")
    parser.add_argument("--fetch", action="store_true", help="Download raw historical match datasets")
    parser.add_argument("--train", action="store_true", help="Train models and compute surface Elo/form features")
    parser.add_argument("--predict", action="store_true", help="Generate predictions for upcoming matches")
    parser.add_argument("--reconcile", action="store_true", help="Reconcile predictions against true match outcomes")
    parser.add_argument("--all", action="store_true", help="Run full pipeline: fetch -> train -> predict -> reconcile")
    parser.add_argument("--force", action="store_true", help="Force redownload of historical datasets")
    
    args = parser.parse_args()

    if len(sys.argv) == 1 or args.all:
        run_data_fetch(force=args.force)
        run_training()
        run_predictions()
        run_reconcile()
    else:
        if args.fetch:
            run_data_fetch(force=args.force)
        if args.train:
            run_training()
        if args.predict:
            run_predictions()
        if args.reconcile:
            run_reconcile()


if __name__ == "__main__":
    main()

