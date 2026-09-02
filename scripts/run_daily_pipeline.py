"""Master Daily Automated Pipeline for Football & Tennis.
Executes:
1. Live Odds & Fixture Sync (The Odds API)
2. Automated Results Verification & Reconciliation (API-Football, The Odds API Scores, Tennis-Data)
3. Cumulative Feature Engineering & Full Model Retraining
4. Artifact Caching for Instant Streamlit Load
"""
import os
import sys
import logging
import json
from datetime import datetime, date
from pathlib import Path

# Add project root, Football, and Tennis directories to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FOOTBALL_DIR = PROJECT_ROOT / "Football"
TENNIS_DIR = PROJECT_ROOT / "Tennis"

for p in [PROJECT_ROOT, FOOTBALL_DIR, TENNIS_DIR]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("DailyPipeline")


def run_tennis_daily_pipeline() -> dict:
    """Execute Tennis daily sync, auto-reconciliation, and model retraining."""
    logger.info("==================================================")
    logger.info("🎾 STARTING TENNIS DAILY AUTOMATION PIPELINE")
    logger.info("==================================================")
    
    from tennis_core.data.scraper import fetch_live_upcoming_fixtures
    from tennis_core.betting.tracker import PredictionTracker
    from tennis_core.models.predictor import TennisPredictor
    from tennis_core.data.auto_reconcile import auto_check_daily_tennis_reconciliation
    from tennis_core.config import CIRCUITS
    from tennis_core.data.preprocessor import load_raw_matches, clean_match_data
    from tennis_core.features.builder import TennisFeaturePipeline
    from tennis_core.models.train import train_tennis_model, save_trained_pipeline

    tracker = PredictionTracker()
    predictor = TennisPredictor()

    # 1. Sync live upcoming fixtures & bookmaker odds
    logger.info(">>> [Tennis 1/3] Syncing live tournament schedules & market odds...")
    fixtures = fetch_live_upcoming_fixtures()
    logger.info(f"Retrieved {len(fixtures)} live tennis fixtures.")

    # 2. Predict and automatically track all fixtures
    for m in fixtures:
        try:
            m_format = 5 if ("Grand Slam" in m.get("tourney_name", "") or "US Open" in m.get("tourney_name", "") or "Wimbledon" in m.get("tourney_name", "") or "Roland Garros" in m.get("tourney_name", "") or "Australian Open" in m.get("tourney_name", "")) and m.get("circuit") == "ATP" else 3
            pred = predictor.predict_match(
                circuit=m.get("circuit", "ATP"),
                p1_name=m.get("p1_name"),
                p2_name=m.get("p2_name"),
                surface=m.get("surface", "Hard"),
                tourney_name=m.get("tourney_name", "Tourney"),
                p1_odds=m.get("p1_odds"),
                p2_odds=m.get("p2_odds"),
                best_of=m_format,
            )
            betting = pred["betting"]
            tracker.log_prediction({
                "match_id": m.get("match_id"),
                "circuit": pred["circuit"],
                "tourney_name": m.get("tourney_name"),
                "surface": pred["surface"],
                "date": m.get("date"),
                "round": m.get("round"),
                "p1_name": pred["p1_name"],
                "p2_name": pred["p2_name"],
                "p1_prob": pred["p1_prob"],
                "p2_prob": pred["p2_prob"],
                "p1_odds": betting.get("p1_odds"),
                "p2_odds": betting.get("p2_odds"),
                "recommended_pick": betting.get("recommended_pick") or pred["predicted_winner"],
                "best_ev": betting.get("best_ev"),
                "best_edge": betting.get("best_edge"),
                "best_stake": betting.get("best_stake"),
                "best_odds": betting.get("best_odds"),
            })
        except Exception as e:
            logger.debug(f"Error predicting tennis match {m.get('p1_name')} vs {m.get('p2_name')}: {e}")

    # 3. Auto-reconcile real match results from The Odds API scores and tennis-data.co.uk
    logger.info(">>> [Tennis 2/3] Reconciling completed match outcomes from official scores...")
    reconcile_res = auto_check_daily_tennis_reconciliation(tracker, force=True)
    logger.info(f"Tennis reconciliation: {reconcile_res.get('reconciled', 0)} newly graded matches. Unverified pending: {reconcile_res.get('pending_past_unverified', 0)}.")

    # 4. Retrain ATP & WTA models with cumulative data
    logger.info(">>> [Tennis 3/3] Retraining ATP & WTA LightGBM models...")
    for circuit in CIRCUITS:
        try:
            raw_df = load_raw_matches(circuit)
            if not raw_df.empty:
                cleaned_df = clean_match_data(raw_df, circuit=circuit)
                pipeline = TennisFeaturePipeline(circuit=circuit)
                X, y = pipeline.process_historical_matches(cleaned_df)
                if not X.empty:
                    model, metrics = train_tennis_model(X, y, circuit=circuit)
                    save_trained_pipeline(pipeline, model, metrics, circuit=circuit)
                    logger.info(f"Successfully retrained and saved {circuit.upper()} pipeline (Accuracy: {metrics.get('accuracy', 0):.3f}).")
        except Exception as e:
            logger.warning(f"Retraining error for {circuit}: {e}")

    logger.info("🎾 TENNIS DAILY PIPELINE COMPLETE!")
    return {
        "fixtures_synced": len(fixtures),
        "reconciled": reconcile_res.get("reconciled", 0),
        "pending_unverified": reconcile_res.get("pending_past_unverified", 0),
    }


def run_football_daily_pipeline() -> dict:
    """Execute Football daily sync, auto-reconciliation, and model retraining."""
    logger.info("==================================================")
    logger.info("⚽ STARTING FOOTBALL DAILY AUTOMATION PIPELINE")
    logger.info("==================================================")

    from football_core.config import LEAGUES
    from football_core.data.odds_api import fetch_all_live_upcoming_fixtures
    from football_core.betting.tracker import PredictionTracker
    from football_core.models.predictor import FootballPredictor
    from football_core.data.api_football import auto_check_daily_reconciliation
    from football_core.data.preprocessor import load_raw_league_data, clean_match_data, save_processed_data
    from football_core.features.builder import FootballFeaturePipeline
    from football_core.models.train import train_league_models, save_trained_bundle

    tracker = PredictionTracker()
    predictor = FootballPredictor()

    # 1. Sync live upcoming fixtures & bookmaker odds
    logger.info(">>> [Football 1/3] Syncing live league fixtures & market odds...")
    fixtures = fetch_all_live_upcoming_fixtures()
    logger.info(f"Retrieved {len(fixtures)} live football fixtures.")

    # 2. Predict and automatically track all fixtures
    for m in fixtures:
        try:
            p = predictor.predict_match(
                league_key=m.get("league_key", "EPL"),
                home_team=m.get("home_team"),
                away_team=m.get("away_team"),
                odds_home=m.get("odds_home"),
                odds_draw=m.get("odds_draw"),
                odds_away=m.get("odds_away"),
                odds_over25=m.get("odds_over25"),
                odds_under25=m.get("odds_under25"),
                odds_btts_yes=m.get("odds_btts_yes"),
                odds_btts_no=m.get("odds_btts_no"),
                odds_corners_over95=m.get("odds_corners_over95"),
                odds_corners_under95=m.get("odds_corners_under95"),
                odds_cards_over35=m.get("odds_cards_over35"),
                odds_cards_under35=m.get("odds_cards_under35"),
            )
            tracker.log_prediction({
                "match_id": m.get("match_id"),
                "league": m.get("league_name", m.get("league_key")),
                "league_key": m.get("league_key"),
                "date": m.get("date"),
                "home_team": m.get("home_team"),
                "away_team": m.get("away_team"),
                "prob_home": p.get("prob_home"),
                "prob_draw": p.get("prob_draw"),
                "prob_away": p.get("prob_away"),
                "prob_over25": p.get("prob_over25"),
                "prob_under25": p.get("prob_under25"),
                "prob_btts_yes": p.get("prob_btts_yes"),
                "prob_btts_no": p.get("prob_btts_no"),
                "prob_corners_over95": p.get("prob_corners_over95"),
                "prob_cards_over35": p.get("prob_cards_over35"),
                "expected_corners": p.get("expected_corners"),
                "expected_cards": p.get("expected_cards"),
                "most_likely_score": p.get("most_likely_score"),
                "odds_home": m.get("odds_home"),
                "odds_draw": m.get("odds_draw"),
                "odds_away": m.get("odds_away"),
                "odds_over25": m.get("odds_over25"),
                "odds_under25": m.get("odds_under25"),
                "odds_btts_yes": m.get("odds_btts_yes"),
                "odds_btts_no": m.get("odds_btts_no"),
            })
        except Exception as e:
            logger.debug(f"Error predicting football match {m.get('home_team')} vs {m.get('away_team')}: {e}")

    # 3. Auto-reconcile real match results from API-Football
    logger.info(">>> [Football 2/3] Reconciling completed match outcomes from official scorecards...")
    reconcile_res = auto_check_daily_reconciliation(tracker, force=True)
    logger.info(f"Football reconciliation: {reconcile_res.get('reconciled', 0)} newly graded matches. Unverified pending: {reconcile_res.get('pending_past_unverified', 0)}.")

    # 4. Retrain 12 League Model Bundles
    logger.info(">>> [Football 3/3] Retraining multi-league LightGBM & Dixon-Coles model bundles...")
    retrained_leagues = 0
    for league_key, league_info in LEAGUES.items():
        if league_info.get("is_cup"):
            continue
        try:
            raw_df = load_raw_league_data(league_key)
            if not raw_df.empty:
                cleaned_df = clean_match_data(raw_df, league_key=league_key)
                save_processed_data(cleaned_df, league_key=league_key)
                pipeline = FootballFeaturePipeline(league_key=league_key)
                X, y = pipeline.process_historical_matches(cleaned_df)
                if not X.empty:
                    models, metrics = train_league_models(X, y, league_key=league_key)
                    save_trained_bundle(pipeline, models, metrics, league_key=league_key)
                    retrained_leagues += 1
        except Exception as e:
            logger.warning(f"Retraining error for league {league_key}: {e}")

    logger.info(f"Successfully retrained {retrained_leagues} league bundles.")
    logger.info("⚽ FOOTBALL DAILY PIPELINE COMPLETE!")
    return {
        "fixtures_synced": len(fixtures),
        "reconciled": reconcile_res.get("reconciled", 0),
        "pending_unverified": reconcile_res.get("pending_past_unverified", 0),
        "retrained_leagues": retrained_leagues,
    }


def main():
    """Run full automated daily workflow."""
    start_time = datetime.now()
    logger.info(f"🚀 Master Sports Analytics Daily Pipeline started at {start_time.isoformat()}")

    t_res = run_tennis_daily_pipeline()
    f_res = run_football_daily_pipeline()

    duration = (datetime.now() - start_time).total_seconds()
    
    meta_path = PROJECT_ROOT / "cache" / "pipeline_run_meta.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "last_successful_run": datetime.now().isoformat(),
            "date": date.today().isoformat(),
            "duration_seconds": round(duration, 1),
            "tennis": t_res,
            "football": f_res,
            "status": "SUCCESS"
        }, f, indent=2)

    logger.info(f"✅ Daily Pipeline completed successfully in {duration:.1f}s!")


if __name__ == "__main__":
    main()
