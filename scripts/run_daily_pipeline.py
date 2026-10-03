"""Master Daily Automated Pipeline for Football & Tennis.

Per sport, in order:
1. Refresh historical results (football-data.co.uk / tennis-data.co.uk).
2. Retrain the models (unless skipped). The feature state is always refreshed; a newly trained
   classifier replaces the deployed one only if its holdout skill against the bookmaker market
   is not worse (see sports_common.evaluation.should_promote).
3. Fetch upcoming fixtures and odds, predict, and log every prediction to the ledger.
4. Reconcile finished matches.
Sports run independently; the run status and the web payload are written at the end.
"""
import os
import sys
import logging
import json
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Any

# Add project root, Football, and Tennis directories to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FOOTBALL_DIR = PROJECT_ROOT / "Football"
TENNIS_DIR = PROJECT_ROOT / "Tennis"

for p in [PROJECT_ROOT, FOOTBALL_DIR, TENNIS_DIR]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from sports_common.secrets import install_log_redaction, redact

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
install_log_redaction()
logger = logging.getLogger("DailyPipeline")

GRAND_SLAMS = ("Grand Slam", "US Open", "Wimbledon", "Roland Garros", "Australian Open")


def retry_operation(func: Callable, name: str, max_retries: int = 3, backoff_factor: int = 5) -> Any:
    """Execute a function with automatic retries and exponential backoff on failure."""
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries:
                logger.error(f"❌ [Retry Failed] '{name}' failed after {max_retries} attempts: {e}")
                raise e
            wait_time = backoff_factor * (2 ** (attempt - 1))
            logger.warning(f"⚠️ [Attempt {attempt}/{max_retries} Failed] '{name}': {e}. Retrying in {wait_time}s...")
            time.sleep(wait_time)


def retrain_requested() -> bool:
    return not (os.environ.get("SKIP_RETRAIN", "").lower() in ("1", "true", "yes") or "--skip-retrain" in sys.argv)


def _log_tennis_predictions(fixtures, predictor, tracker) -> dict:
    """Predict each tennis fixture and log it to the tracker. Returns success/failure counts."""
    logged, failures = 0, []
    for m in fixtures:
        try:
            is_slam = any(name in m.get("tourney_name", "") for name in GRAND_SLAMS)
            pred = predictor.predict_match(
                circuit=m.get("circuit", "ATP"),
                p1_name=m.get("p1_name"),
                p2_name=m.get("p2_name"),
                surface=m.get("surface", "Hard"),
                p1_odds=m.get("p1_odds"),
                p2_odds=m.get("p2_odds"),
                best_of=5 if (is_slam and m.get("circuit") == "ATP") else 3,
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
                "sets_games": pred.get("sets_games"),
            })
            logged += 1
        except Exception as e:
            failures.append(f"{m.get('p1_name')} vs {m.get('p2_name')}: {type(e).__name__}: {e}")
    return {"logged": logged, "failed": len(failures), "failure_samples": failures[:5]}


def _log_football_predictions(fixtures, predictor, tracker, LEAGUES) -> dict:
    """Predict each football fixture and log it (with the market prices used). Returns counts."""
    logged, failures = 0, []
    for m in fixtures:
        try:
            l_key = m.get("league_key") or m.get("league") or "EPL"
            tourn = m.get("league_name") or LEAGUES.get(l_key, {}).get("name")
            is_neut = bool(m.get("is_neutral") if m.get("is_neutral") is not None else m.get("neutral", False))

            p = predictor.predict_match(
                league_key=l_key,
                home_team=m.get("home_team"),
                away_team=m.get("away_team"),
                referee=m.get("referee"),
                is_neutral=is_neut,
                tournament=tourn,
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
                match_date=m.get("date"),
            )
            tracker.log_prediction({
                "match_id": m.get("match_id"),
                "league": m.get("league_name") or m.get("league") or l_key,
                "league_key": l_key,
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
                "expected_goals_home": p.get("expected_goals_home"),
                "expected_goals_away": p.get("expected_goals_away"),
                "most_likely_score": p.get("most_likely_score"),
                "best_pick": p.get("best_pick"),
                "has_value": p.get("has_value"),
                "referee": p.get("referee"),
                "odds_home": m.get("odds_home"),
                "odds_draw": m.get("odds_draw"),
                "odds_away": m.get("odds_away"),
                "odds_over25": m.get("odds_over25"),
                "odds_under25": m.get("odds_under25"),
                "odds_btts_yes": m.get("odds_btts_yes"),
                "odds_btts_no": m.get("odds_btts_no"),
                "bookmaker": m.get("bookmaker"),
            })
            logged += 1
        except Exception as e:
            failures.append(f"{m.get('home_team')} vs {m.get('away_team')}: {type(e).__name__}: {e}")
    return {"logged": logged, "failed": len(failures), "failure_samples": failures[:5]}


def _report_failures(sport: str, stats: dict, total: int) -> None:
    if stats["failed"]:
        logger.warning(f"{sport}: {stats['failed']}/{total} predictions failed, e.g. {stats['failure_samples'][:3]}")


def run_tennis_daily_pipeline() -> dict:
    """Execute Tennis model retraining, fixture sync, prediction logging and reconciliation."""
    logger.info("==================================================")
    logger.info("🎾 STARTING TENNIS DAILY AUTOMATION PIPELINE")
    logger.info("==================================================")

    from tennis_core.data.scraper import fetch_live_upcoming_fixtures
    from tennis_core.betting.tracker import PredictionTracker
    from tennis_core.data.auto_reconcile import auto_check_daily_tennis_reconciliation
    from tennis_core.config import CIRCUITS
    from tennis_core.data.preprocessor import load_raw_matches, clean_match_data
    from tennis_core.models.train import retrain_circuit

    # 1. Retrain ATP & WTA (feature state always refreshed; classifier promotion is gated)
    retrain_results = []
    if retrain_requested():
        logger.info(">>> [Tennis 1/3] Retraining ATP & WTA models...")
        for circuit in CIRCUITS:
            try:
                raw_df = load_raw_matches(circuit)
                if raw_df.empty:
                    continue
                retrain_results.append(retrain_circuit(circuit, clean_match_data(raw_df, circuit=circuit)))
                logger.info(f"{circuit.upper()} retrain: {retrain_results[-1]['status']} ({retrain_results[-1]['reason']})")
            except Exception as e:
                logger.warning(f"Retraining error for {circuit}: {redact(e)}")
                retrain_results.append({"circuit": circuit, "status": "error", "reason": redact(e)})
    else:
        logger.info(">>> [Tennis 1/3] Model retraining skipped (SKIP_RETRAIN active).")

    from tennis_core.models.predictor import TennisPredictor
    tracker = PredictionTracker()
    predictor = TennisPredictor()

    # 2. Sync fixtures & odds, predict, and log (single ledger write)
    logger.info(">>> [Tennis 2/3] Syncing live tournament schedules & market odds...")
    fixtures = retry_operation(lambda: fetch_live_upcoming_fixtures(), name="Tennis Fetch Upcoming Fixtures")
    logger.info(f"Retrieved {len(fixtures)} live tennis fixtures.")
    with tracker.batch():
        pred_stats = _log_tennis_predictions(fixtures, predictor, tracker)
    _report_failures("Tennis", pred_stats, len(fixtures))

    # 3. Reconcile completed matches (The Odds API scores, tennis-data.co.uk, ESPN)
    logger.info(">>> [Tennis 3/3] Reconciling completed match outcomes from official scores...")
    reconcile_res = retry_operation(lambda: auto_check_daily_tennis_reconciliation(tracker, force=True), name="Tennis Reconcile Results")
    logger.info(f"Tennis reconciliation: {reconcile_res.get('reconciled', 0)} newly graded matches. Unverified pending: {reconcile_res.get('pending_past_unverified', 0)}.")

    logger.info("🎾 TENNIS DAILY PIPELINE COMPLETE!")
    return {
        "status": "SUCCESS",
        "fixtures_synced": len(fixtures),
        "predictions_logged": pred_stats["logged"],
        "prediction_failures": pred_stats["failed"],
        "reconciled": reconcile_res.get("reconciled", 0),
        "pending_unverified": reconcile_res.get("pending_past_unverified", 0),
        "retrain": retrain_results,
    }


def run_football_daily_pipeline() -> dict:
    """Execute Football data refresh, model retraining, fixture sync, prediction logging and reconciliation."""
    logger.info("==================================================")
    logger.info("⚽ STARTING FOOTBALL DAILY AUTOMATION PIPELINE")
    logger.info("==================================================")

    from football_core.config import LEAGUES
    from football_core.data.odds_api import fetch_all_live_upcoming_fixtures
    from football_core.betting.tracker import PredictionTracker
    from football_core.data.api_football import auto_check_daily_reconciliation
    from football_core.data.preprocessor import load_raw_league_data, clean_match_data, save_processed_data
    from football_core.models.train import retrain_league

    # 0. Refresh active seasons match data from football-data.co.uk & Understat xG
    logger.info(">>> [Football 0/3] Updating latest match data from football-data.co.uk & Understat xG...")
    try:
        from football_core.data.fetcher import update_active_seasons
        update_active_seasons()
    except Exception as e:
        logger.warning(f"Could not refresh active seasons: {redact(e)}")

    try:
        from football_core.data.xg_scraper import update_xg_data
        update_xg_data()
    except Exception as e:
        logger.warning(f"Could not refresh Understat xG: {redact(e)}")

    # 1. Retrain domestic league bundles (feature state always refreshed; promotion is gated)
    retrain_results = []
    if retrain_requested():
        logger.info(">>> [Football 1/3] Retraining league models...")
        for league_key, league_info in LEAGUES.items():
            if league_info.get("is_cup") or league_info.get("is_international"):
                continue
            try:
                raw_df = load_raw_league_data(league_key)
                if raw_df.empty:
                    continue
                cleaned_df = clean_match_data(raw_df, league_key=league_key)
                save_processed_data(cleaned_df, league_key=league_key)
                retrain_results.append(retrain_league(league_key, cleaned_df))
                logger.info(f"{league_key} retrain: {retrain_results[-1]['status']} ({retrain_results[-1]['reason']})")
            except Exception as e:
                logger.warning(f"Retraining error for league {league_key}: {redact(e)}")
                retrain_results.append({"league": league_key, "status": "error", "reason": redact(e)})
    else:
        logger.info(">>> [Football 1/3] Model retraining skipped (SKIP_RETRAIN active).")

    from football_core.models.predictor import FootballPredictor
    predictor = FootballPredictor()
    tracker = PredictionTracker()
    tracker.upgrade_ledger()

    # 2. Sync fixtures & odds, predict, and log (single ledger write)
    logger.info(">>> [Football 2/3] Syncing live league fixtures & market odds...")
    fixtures = retry_operation(lambda: fetch_all_live_upcoming_fixtures(), name="Football Fetch Upcoming Fixtures")
    logger.info(f"Retrieved {len(fixtures)} live football fixtures.")
    with tracker.batch():
        pred_stats = _log_football_predictions(fixtures, predictor, tracker, LEAGUES)
    _report_failures("Football", pred_stats, len(fixtures))

    # 3. Reconcile completed matches (API-Football when a key is configured, then ESPN)
    logger.info(">>> [Football 3/3] Reconciling completed match outcomes from official scorecards...")
    reconcile_res = retry_operation(lambda: auto_check_daily_reconciliation(tracker, force=True), name="Football Reconcile Results")
    logger.info(f"Football reconciliation: {reconcile_res.get('reconciled', 0)} newly graded matches. Unverified pending: {reconcile_res.get('pending_past_unverified', 0)}.")
    try:
        from football_core.data.espn_client import reconcile_tracker_with_espn, backfill_missing_corners_cards
        espn_rec = reconcile_tracker_with_espn(tracker)
        espn_backfill = backfill_missing_corners_cards(tracker)
        logger.info(f"ESPN reconciliation: {espn_rec} graded, {espn_backfill} enriched with corners/cards.")
    except Exception as e:
        logger.warning(f"ESPN reconciliation warning: {redact(e)}")

    logger.info("⚽ FOOTBALL DAILY PIPELINE COMPLETE!")
    return {
        "status": "SUCCESS",
        "fixtures_synced": len(fixtures),
        "predictions_logged": pred_stats["logged"],
        "prediction_failures": pred_stats["failed"],
        "reconciled": reconcile_res.get("reconciled", 0),
        "pending_unverified": reconcile_res.get("pending_past_unverified", 0),
        "retrain": retrain_results,
    }


def _sport_status(result: dict, max_failure_share: float = 0.2) -> str:
    """SUCCESS, or PARTIAL when too many predictions failed, or the sport's own FAILED/SKIPPED."""
    if result.get("status") != "SUCCESS":
        return result.get("status", "FAILED")
    total = result.get("predictions_logged", 0) + result.get("prediction_failures", 0)
    if total and result.get("prediction_failures", 0) / total > max_failure_share:
        return "PARTIAL"
    return "SUCCESS"


def main():
    """Run full automated daily workflow with error isolation and health reporting."""
    start_time = datetime.now(timezone.utc)
    logger.info(f"🚀 Master Sports Analytics Daily Pipeline started at {start_time.isoformat()}")

    errors = []
    t_res = {"status": "SKIPPED"}
    f_res = {"status": "SKIPPED"}

    # Run Tennis
    try:
        t_res = run_tennis_daily_pipeline()
    except Exception as e:
        err_msg = redact(f"Tennis Pipeline Failed: {e}\n{traceback.format_exc()}")
        logger.error(err_msg)
        errors.append(err_msg)
        t_res = {"status": "FAILED", "error": redact(e)}

    # Run Football
    try:
        f_res = run_football_daily_pipeline()
    except Exception as e:
        err_msg = redact(f"Football Pipeline Failed: {e}\n{traceback.format_exc()}")
        logger.error(err_msg)
        errors.append(err_msg)
        f_res = {"status": "FAILED", "error": redact(e)}

    finished = datetime.now(timezone.utc)
    duration = (finished - start_time).total_seconds()
    statuses = [_sport_status(t_res), _sport_status(f_res)]
    if all(s == "SUCCESS" for s in statuses):
        overall_status = "SUCCESS"
    elif all(s == "FAILED" for s in statuses):
        overall_status = "FAILED"
    else:
        overall_status = "PARTIAL_SUCCESS"

    meta_path = PROJECT_ROOT / "cache" / "pipeline_run_meta.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "last_run_timestamp": finished.isoformat(timespec="seconds"),
            "date": finished.date().isoformat(),
            "duration_seconds": round(duration, 1),
            "status": overall_status,
            "tennis": t_res,
            "football": f_res,
            "errors": errors
        }, f, indent=2)

    # Generate consolidated payload for the web frontend
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        from export_web_data import build_web_payload
        build_web_payload()
    except Exception as e:
        logger.warning(f"Could not build web payload: {redact(e)}")

    if overall_status != "SUCCESS":
        logger.warning(f"⚠️ Daily Pipeline finished with status {overall_status} in {duration:.1f}s.")
        if overall_status == "FAILED":
            sys.exit(1)
    else:
        logger.info(f"✅ Daily Pipeline completed successfully in {duration:.1f}s!")


if __name__ == "__main__":
    main()
