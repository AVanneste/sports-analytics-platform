"""Command-Line Pipeline Runner for PitchVision Football Engine."""
import argparse
import logging
import sys
from pathlib import Path
import pandas as pd

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from football_core.config import LEAGUES
from football_core.data.fetcher import fetch_all_data
from football_core.data.preprocessor import clean_match_data, load_raw_league_data, save_processed_data
from football_core.features.builder import FootballFeaturePipeline
from football_core.models.train import train_league_models, save_trained_bundle
from football_core.models.predictor import FootballPredictor
from football_core.data.odds_api import fetch_all_live_upcoming_fixtures
from football_core.betting.tracker import PredictionTracker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def run_data_fetch(force: bool = False):
    """Step 1: Download all national leagues historical datasets."""
    logger.info(">>> STEP 1: Fetching historical football data from football-data.co.uk...")
    fetch_all_data(force=force)


def run_training():
    """Step 2: Clean data, compute dynamic features (Elo, Dixon-Coles, Form, H2H, Corners, Cards), train & calibrate LightGBM."""
    logger.info(">>> STEP 2: Building features and training models for all national leagues...")
    
    for league_key, league_info in LEAGUES.items():
        if league_info.get("is_cup"):
            continue

        logger.info(f"\n==========================================")
        logger.info(f"--- Training {league_info['name']} ({league_key}) Pipeline ---")
        logger.info(f"==========================================")
        
        raw_df = load_raw_league_data(league_key)
        if raw_df.empty:
            logger.warning(f"No raw match data found for {league_key}. Run with --fetch first!")
            continue

        cleaned_df = clean_match_data(raw_df, league_key=league_key)
        if cleaned_df.empty:
            logger.warning(f"Failed to clean data for {league_key}.")
            continue
        save_processed_data(cleaned_df, league_key)

        # Build features chronologically
        pipeline = FootballFeaturePipeline(league_key=league_key)
        X, y = pipeline.process_historical_matches(cleaned_df)

        if X.empty:
            logger.warning(f"Could not build features for {league_key}")
            continue

        # Train and calibrate models
        models, metrics = train_league_models(X, y, league_key=league_key)

        # Save model bundle
        save_trained_bundle(pipeline, models, metrics, league_key=league_key)

    logger.info("\n>>> Model training and artifact saving complete across all leagues!")


def run_predictions():
    """Step 3: Generate predictions for upcoming fixtures and log to tracker."""
    logger.info(">>> STEP 3: Predicting outcomes for upcoming fixtures...")
    predictor = FootballPredictor()
    tracker = PredictionTracker()

    upcoming_fixtures = fetch_all_live_upcoming_fixtures(use_cache=False)
    if not upcoming_fixtures:
        logger.info("No live fixtures retrieved from API.")
        return

    logger.info(f"Loaded {len(upcoming_fixtures)} upcoming fixtures.")

    for match in upcoming_fixtures:
        league_key = match.get("league")
        if not predictor.is_league_ready(league_key):
            continue

        try:
            pred = predictor.predict_match(
                league_key=league_key,
                home_team=match["home_team"],
                away_team=match["away_team"],
                odds_home=match.get("odds_home"),
                odds_draw=match.get("odds_draw"),
                odds_away=match.get("odds_away"),
                odds_over25=match.get("odds_over25"),
                odds_under25=match.get("odds_under25"),
            )

            pred["fixture_meta"] = match
            tracker.log_full_match_prediction(pred)
            logger.info(f"Logged prediction: {pred['home_team']} vs {pred['away_team']} -> Score: {pred['most_likely_score']}, 1X2: {pred['prob_home']*100:.1f}%/{pred['prob_draw']*100:.1f}%/{pred['prob_away']*100:.1f}%")
        except Exception as e:
            logger.warning(f"Error predicting match {match.get('home_team')} vs {match.get('away_team')}: {e}")

    logger.info(">>> Prediction step complete!")


def main():
    parser = argparse.ArgumentParser(description="PitchVision Football Prediction & Value Engine Pipeline")
    parser.add_argument("--fetch", action="store_true", help="Download raw historical datasets")
    parser.add_argument("--train", action="store_true", help="Train and calibrate models for all leagues")
    parser.add_argument("--predict", action="store_true", help="Run inference on upcoming matches")
    parser.add_argument("--force", action="store_true", help="Force redownload of historical data")
    parser.add_argument("--all", action="store_true", help="Run full pipeline end-to-end")

    args = parser.parse_args()

    run_all = args.all or not (args.fetch or args.train or args.predict)

    if args.fetch or run_all:
        run_data_fetch(force=args.force)

    if args.train or run_all:
        run_training()

    if args.predict or run_all:
        run_predictions()


if __name__ == "__main__":
    main()
