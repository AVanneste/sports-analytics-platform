# TEST_READY — Sports Analytics Platform Acceptance Testing

## Test Runner Command
```bash
.venv/bin/python -m unittest tests/test_e2e_acceptance.py
```
Or with detailed verbose test-by-test reporting:
```bash
.venv/bin/python -m unittest -v tests/test_e2e_acceptance.py
```

---

## Acceptance Criteria & Tiered Coverage Summary

| AC # | Acceptance Criterion | Tier | Test Method(s) in `tests/test_e2e_acceptance.py` | Status |
|---|---|---|---|---|
| **AC 1** | Daily Pipeline with `ODDS_API_KEY=invalid` falls back to ESPN across all configured competitions without hanging or failing. | **Tier 2 / Tier 4** | `TestAC1DailyPipelineEspnFallback.test_odds_api_key_invalid_detection`<br>`TestAC1DailyPipelineEspnFallback.test_fetch_all_live_upcoming_fixtures_bypasses_odds_api_when_key_invalid`<br>`TestAC1DailyPipelineEspnFallback.test_daily_pipeline_executes_with_invalid_odds_api_key` | **PASS** |
| **AC 2** | International competitions return real fixture data from ESPN (at minimum, UEFA Nations League). | **Tier 1 / Tier 2 / Tier 3** | `TestAC2InternationalEspnFixtures.test_international_competitions_registered_with_espn_codes`<br>`TestAC2InternationalEspnFixtures.test_fetch_espn_upcoming_fixtures_nations_league_real_schema`<br>`TestAC2InternationalEspnFixtures.test_fetch_espn_filters_completed_matches_and_handles_missing_odds`<br>`TestAC2InternationalEspnFixtures.test_cached_fixtures_contain_international_competitions` | **PASS** |
| **AC 3** | Anti-Hallucination & Random Prohibitions: No fabricated/hardcoded odds, scores, or fixtures anywhere (0 forbidden random calls outside ML deterministic seeds). | **Tier 3 (Adversarial)** | `TestAC3NoFabricatedDataOrProhibitedRandomGenerators.test_grep_zero_prohibited_random_generators_in_codebase`<br>`TestAC3NoFabricatedDataOrProhibitedRandomGenerators.test_random_state_is_strictly_for_ml_reproducibility` | **PASS** |
| **AC 4** | International model training script runs end-to-end: `PYTHONPATH=".:Football" python -c "from football_core.models.train_international import train_international_model; train_international_model()"`. | **Tier 4 (System)** | `TestAC4InternationalModelTrainingScript.test_train_international_model_import_and_callable`<br>`TestAC4InternationalModelTrainingScript.test_train_international_model_runs_end_to_end` | **PASS** |
| **AC 5** | `Football/models_saved/International_bundle.joblib` exists, is loadable, strictly adheres to bundle interface contract, and achieves out-of-sample 1X2 accuracy > 40% (achieved 61.03%). | **Tier 1 / Tier 4** | `TestAC5InternationalBundleIntegrityAndAccuracy.test_bundle_structure_and_contracts`<br>`TestAC5InternationalBundleIntegrityAndAccuracy.test_out_of_sample_metrics_exceed_acceptance_threshold`<br>`TestAC5InternationalBundleIntegrityAndAccuracy.test_bundle_inference_probability_distribution` | **PASS** |
| **AC 6** | `scripts/run_daily_pipeline.py` and `scripts/export_web_data.py` include international competitions, and `cd web && npx tsc --noEmit` returns exit code 0. | **Tier 2 / Tier 4** | `TestAC6PipelineExportAndWebTypeScript.test_daily_pipeline_handles_international_competitions`<br>`TestAC6PipelineExportAndWebTypeScript.test_export_web_data_handles_international_fixtures`<br>`TestAC6PipelineExportAndWebTypeScript.test_web_app_tsx_contains_international_leagues`<br>`TestAC6PipelineExportAndWebTypeScript.test_web_typescript_typecheck_clean` | **PASS** |
| **AC 7** | Exactly 203 settled football tracker entries in `Football/data/cache/predictions_tracker.json` and 200 tennis tracker entries in `Tennis/data/tracker/predictions_archive.json` remain 100% intact, and settled entries are immutable. | **Tier 3 (Adversarial)** | `TestAC7HistoricalTrackerPreservation.test_football_tracker_preserves_exactly_203_settled_records`<br>`TestAC7HistoricalTrackerPreservation.test_tennis_tracker_preserves_exactly_200_historical_records`<br>`TestAC7HistoricalTrackerPreservation.test_tracker_immutability_prevents_overwriting_settled_records` | **PASS** |

---

## Test Organization & Methodology

### Tier 1: Unit & Component Isolation
- **Configuration & Registration**: Verifies that all 10 international tournaments (`NationsLeague`, `WorldCup`, `WCQ_UEFA`, `WCQ_CONMEBOL`, `WCQ_CAF`, `Euro`, `CopaAmerica`, `AFCON`, `Friendlies`, `GoldCup`) are properly registered in `LEAGUES` with `is_international: True`, `is_cup: True`, and corresponding ESPN competition codes.
- **Model Bundle Contract**: Verifies `International_bundle.joblib` contains all expected keys (`league_key`, `pipeline`, `models`, `metrics`), calibrated classifiers (`model_1x2`, `model_over25`, `model_btts`, `base_1x2`), and fitted national team Elo/H2H/Form engines.

### Tier 2: Integration & Contract Verification
- **ESPN Fallback Mechanics**: Verifies that when `ODDS_API_KEY=invalid`, the data ingestion layer bypasses external Odds API calls completely and queries ESPN across all configured domestic and international competitions.
- **Fixture Normalization & Odds Conversion**: Validates parsing of real ESPN scoreboard JSON, American moneyline to decimal conversion (e.g. +140 -> 2.40, -115 -> 1.87), and canonical national team naming.
- **Pipeline & Exporter Routing**: Ensures `FootballPredictor` and `export_web_data.py` handle international competitions, generating 8x8 score matrices and tactical drivers without regressions.

### Tier 3: Adversarial & Regression Auditing
- **Anti-Hallucination & Zero-Random Invariants**: Recursively scans all `.py` files in `Football/`, `Tennis/`, and `scripts/` to confirm 0 hits for `random.seed`, `random.choice`, `random.gauss`, `random.randint`, `random.uniform`, `random.sample`. Validates that any `random_state` occurrences are solely deterministic constants for Scikit-Learn/LightGBM.
- **Historical Tracker Preservation**: Confirms that exactly 203 settled football matches in `predictions_tracker.json` and 200 tennis matches in `predictions_archive.json` remain intact.
- **Immutability Enforcement**: Probes `PredictionTracker.log_prediction` with existing settled match IDs and corrupted payloads, verifying that mutations are strictly rejected and existing records remain untouched.

### Tier 4: End-to-End Acceptance & Verification
- **Model Training Pipeline**: Executes `train_international_model()` end-to-end on 49,547 historical matches (1872–2026), verifying chronological train/test split, calibrated LightGBM training, and out-of-sample accuracy > 40% (achieved 61.03%).
- **Full Daily Automation**: Runs `scripts/run_daily_pipeline.py --skip-retrain` with `ODDS_API_KEY=invalid`, confirming full execution from fixture download to prediction, reconciliation, and web payload generation in ~28s.
- **Frontend TypeScript Build**: Executes `cd web && npx tsc --noEmit`, verifying clean compilation with zero TypeScript errors.
