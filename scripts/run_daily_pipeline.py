"""Master Daily Automated Pipeline for Football & Tennis.

Per sport, in order:
1. Refresh historical results (football-data.co.uk / tennis-data.co.uk).
2. Retrain weekly (RETRAIN_WEEKDAY, default Monday UTC), when forced (FORCE_RETRAIN=1 or
   --force-retrain), or when a deployed model is missing, stale or from an older feature schema.
   A new classifier replaces the deployed one only if its holdout skill against the bookmaker
   market is not worse (sports_common.evaluation.should_promote). On other days only the
   feature state (ratings, form, Dixon-Coles) is rebuilt in memory, so nothing is committed.
3. Fetch upcoming fixtures and odds, predict, and log every prediction to the ledger.
4. Reconcile finished matches.
Sports run independently; the run status and the web payload are written at the end.
SKIP_RETRAIN=1 (or --skip-retrain) disables retraining entirely.
"""
import os
import sys
import logging
import json
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional, Tuple

# Packages come from the editable install (pip install -e .); see README.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

from sports_common.jsonstore import read_json
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


RETRAIN_WEEKDAY = int(os.environ.get("RETRAIN_WEEKDAY", "0"))  # 0 = Monday (UTC)
MAX_MODEL_AGE_DAYS = 8


def _flag(name: str, cli: str) -> bool:
    return os.environ.get(name, "").lower() in ("1", "true", "yes") or cli in sys.argv


def retrain_decision(metrics: Dict[str, Any], keys: Iterable[str], schema_version: int) -> Tuple[bool, str]:
    """Whether today's run should retrain, and why."""
    if _flag("SKIP_RETRAIN", "--skip-retrain"):
        return False, "skipped (SKIP_RETRAIN)"
    if _flag("FORCE_RETRAIN", "--force-retrain"):
        return True, "forced"
    now = datetime.now(timezone.utc)
    if now.weekday() == RETRAIN_WEEKDAY:
        return True, "weekly schedule"
    for key in keys:
        m = (metrics or {}).get(key)
        if not m:
            return True, f"no deployed model for {key}"
        if m.get("schema_version") != schema_version:
            return True, f"{key} model uses an older feature schema"
        try:
            age = (now - datetime.fromisoformat(m.get("checked_at") or m.get("trained_at"))).days
        except (TypeError, ValueError):
            return True, f"{key} model has no usable training timestamp"
        if age > MAX_MODEL_AGE_DAYS:
            return True, f"{key} model is {age} days old"
    return False, "deployed models are current; feature state refreshed in memory"


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
                "p1_model_prob": pred.get("p1_model_prob"),
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
                "model_prob_home": p.get("model_prob_home"),
                "model_prob_draw": p.get("model_prob_draw"),
                "model_prob_away": p.get("model_prob_away"),
                "model_prob_over25": p.get("model_prob_over25"),
                "low_confidence": p.get("low_confidence"),
                "referee": p.get("referee"),
                "odds_home": m.get("odds_home"),
                "odds_draw": m.get("odds_draw"),
                "odds_away": m.get("odds_away"),
                "odds_over25": m.get("odds_over25"),
                "odds_under25": m.get("odds_under25"),
                "odds_btts_yes": m.get("odds_btts_yes"),
                "odds_btts_no": m.get("odds_btts_no"),
                "odds_corners_over95": m.get("odds_corners_over95"),
                "odds_corners_under95": m.get("odds_corners_under95"),
                "bookmaker": m.get("bookmaker"),
                "reference_odds": m.get("reference_odds"),
                "kambi_event_id": m.get("kambi_event_id"),
            })
            logged += 1
        except Exception as e:
            failures.append(f"{m.get('home_team')} vs {m.get('away_team')}: {type(e).__name__}: {e}")
    return {"logged": logged, "failed": len(failures), "failure_samples": failures[:5]}


def _report_failures(sport: str, stats: dict, total: int) -> None:
    if stats["failed"]:
        logger.warning(f"{sport}: {stats['failed']}/{total} predictions failed, e.g. {stats['failure_samples'][:3]}")


def run_tennis_daily_pipeline() -> Tuple[dict, Any]:
    """Execute Tennis model retraining, fixture sync, prediction logging and reconciliation."""
    logger.info("==================================================")
    logger.info("🎾 STARTING TENNIS DAILY AUTOMATION PIPELINE")
    logger.info("==================================================")

    from tennis_core.data.scraper import fetch_live_upcoming_fixtures
    from tennis_core.betting.tracker import PredictionTracker
    from tennis_core.data.auto_reconcile import auto_check_daily_tennis_reconciliation
    from tennis_core.config import CIRCUITS, METRICS_PATH
    from tennis_core.data.preprocessor import load_raw_matches, clean_match_data
    from tennis_core.features.builder import FEATURE_SCHEMA_VERSION
    from tennis_core.models.train import retrain_circuit

    # tennis-data.co.uk refuses this job's servers: fill the recent weeks from ESPN's results
    from tennis_core.data.espn_results import update_espn_results
    for circuit in CIRCUITS:
        try:
            update_espn_results(circuit, load_raw_matches(circuit, include_espn=False))
        except Exception as e:
            logger.warning(f"Could not refresh ESPN {circuit.upper()} results: {redact(e)}")

    raw = {circuit: load_raw_matches(circuit) for circuit in CIRCUITS}
    raw = {circuit: df for circuit, df in raw.items() if not df.empty}

    # Birth dates for the age features: Wikidata, matched to tennis-data names (weekly)
    from tennis_core.data.birthdates import update_birthdates
    try:
        update_birthdates(raw)
    except Exception as e:
        logger.warning(f"Could not refresh Wikidata birth dates: {redact(e)}")

    cleaned: Dict[str, Any] = {circuit: clean_match_data(df, circuit=circuit) for circuit, df in raw.items()}

    # 1. Retrain ATP & WTA when due (classifier promotion is gated)
    due, why = retrain_decision(read_json(METRICS_PATH, default={}), list(cleaned), FEATURE_SCHEMA_VERSION)
    retrain_results = []
    logger.info(f">>> [Tennis 1/3] Retrain due: {due} ({why})")
    if due:
        for circuit, cleaned_df in cleaned.items():
            try:
                retrain_results.append(retrain_circuit(circuit, cleaned_df))
                logger.info(f"{circuit.upper()} retrain: {retrain_results[-1]['status']} ({retrain_results[-1]['reason']})")
            except Exception as e:
                logger.warning(f"Retraining error for {circuit}: {redact(e)}")
                retrain_results.append({"circuit": circuit, "status": "error", "reason": redact(e)})

    from tennis_core.models.predictor import TennisPredictor
    tracker = PredictionTracker()
    predictor = TennisPredictor()
    if not due:
        for circuit, cleaned_df in cleaned.items():
            predictor.refresh_state(circuit, cleaned_df)

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
        "retrain": {"due": due, "reason": why, "results": retrain_results},
    }, predictor


def run_football_daily_pipeline() -> Tuple[dict, Any]:
    """Execute Football data refresh, model retraining, fixture sync, prediction logging and reconciliation."""
    logger.info("==================================================")
    logger.info("⚽ STARTING FOOTBALL DAILY AUTOMATION PIPELINE")
    logger.info("==================================================")

    from football_core.config import LEAGUES
    from football_core.data.odds_api import fetch_all_live_upcoming_fixtures
    from football_core.betting.tracker import PredictionTracker
    from football_core.data.api_football import auto_check_daily_reconciliation
    from football_core.data.preprocessor import load_raw_league_data, clean_match_data
    from football_core.features.builder import FEATURE_SCHEMA_VERSION
    from football_core.models.train import METRICS_FILE, retrain_league

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

    try:
        from football_core.data.fotmob_xg import update_fotmob_xg
        update_fotmob_xg()
    except Exception as e:
        logger.warning(f"Could not refresh FotMob xG: {redact(e)}")

    try:  # one rating scale across leagues, for European cup ties
        from football_core.data.opta_power import update_power_rankings
        update_power_rankings()
    except Exception as e:
        logger.warning(f"Could not refresh Opta Power Rankings: {redact(e)}")

    cleaned: Dict[str, Any] = {}
    for league_key, league_info in LEAGUES.items():
        if league_info.get("is_cup") or league_info.get("is_international"):
            continue
        try:
            raw_df = load_raw_league_data(league_key)
            if not raw_df.empty:
                cleaned[league_key] = clean_match_data(raw_df, league_key=league_key)
        except Exception as e:
            logger.warning(f"Could not load {league_key} results: {redact(e)}")

    # 1. Retrain domestic league bundles when due (classifier promotion is gated)
    due, why = retrain_decision(read_json(METRICS_FILE, default={}), list(cleaned), FEATURE_SCHEMA_VERSION)
    retrain_results = []
    logger.info(f">>> [Football 1/3] Retrain due: {due} ({why})")
    if due:
        for league_key, cleaned_df in cleaned.items():
            try:
                retrain_results.append(retrain_league(league_key, cleaned_df))
                logger.info(f"{league_key} retrain: {retrain_results[-1]['status']} ({retrain_results[-1]['reason']})")
            except Exception as e:
                logger.warning(f"Retraining error for league {league_key}: {redact(e)}")
                retrain_results.append({"league": league_key, "status": "error", "reason": redact(e)})

    from football_core.models.predictor import FootballPredictor
    predictor = FootballPredictor()
    if not due:
        for league_key, cleaned_df in cleaned.items():
            predictor.refresh_state(league_key, cleaned_df)
    tracker = PredictionTracker()
    tracker.upgrade_ledger()

    # 2. Sync fixtures & odds, predict, and log (single ledger write)
    logger.info(">>> [Football 2/3] Syncing live league fixtures & market odds...")
    fixtures = retry_operation(lambda: fetch_all_live_upcoming_fixtures(), name="Football Fetch Upcoming Fixtures")
    logger.info(f"Retrieved {len(fixtures)} live football fixtures.")
    with tracker.batch():
        pred_stats = _log_football_predictions(fixtures, predictor, tracker, LEAGUES)
    _report_failures("Football", pred_stats, len(fixtures))

    # Closing Belgian prices from the hourly archive (odds-archive branch), before settling
    try:
        from football_core.data.odds_archive import recent_closing_prices
        logger.info(f"Closing Belgian prices attached to {tracker.attach_closing_odds(recent_closing_prices())} predictions.")
    except Exception as e:
        logger.warning(f"Could not attach closing prices: {redact(e)}")

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
        "retrain": {"due": due, "reason": why, "results": retrain_results},
    }, predictor


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
    tn_predictor = fb_predictor = None

    # Run Tennis
    try:
        t_res, tn_predictor = run_tennis_daily_pipeline()
    except Exception as e:
        err_msg = redact(f"Tennis Pipeline Failed: {e}\n{traceback.format_exc()}")
        logger.error(err_msg)
        errors.append(err_msg)
        t_res = {"status": "FAILED", "error": redact(e)}

    # Run Football
    try:
        f_res, fb_predictor = run_football_daily_pipeline()
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
        from export_web_data import build_web_payload  # sibling script in scripts/
        build_web_payload(fb_predictor=fb_predictor, tn_predictor=tn_predictor)
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
