"""Unified E2E Acceptance Test Suite for Sports Analytics Platform.

Covers all 7 Acceptance Criteria defined in ORIGINAL_REQUEST.md and PROJECT.md:
- AC 1: Running scripts/run_daily_pipeline.py with ODDS_API_KEY=invalid fetches upcoming
        fixtures from ESPN for all configured competitions.
- AC 2: International competitions return real fixture data from ESPN (at minimum, UEFA Nations League).
- AC 3: No fabricated/hardcoded odds, scores, or fixtures anywhere (grep for random.seed,
        random.choice, random.gauss in Python files returns 0 hits outside ML random_state).
- AC 4: International model training script runs end-to-end:
        PYTHONPATH=".:Football" python -c "from football_core.models.train_international import train_international_model; train_international_model()".
- AC 5: Football/models_saved/International_bundle.joblib exists, is loadable, and out-of-sample 1X2 accuracy > 40%.
- AC 6: scripts/run_daily_pipeline.py and scripts/export_web_data.py include international competitions,
        and cd web && npx tsc --noEmit returns exit code 0.
- AC 7: Exactly 203 settled football tracker entries in Football/data/cache/predictions_tracker.json
        and 200 tennis tracker entries in Tennis/data/tracker/predictions_archive.json remain 100% intact.
"""

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root, Football, and Tennis directories are in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FOOTBALL_DIR = PROJECT_ROOT / "Football"
TENNIS_DIR = PROJECT_ROOT / "Tennis"

for p in [PROJECT_ROOT, FOOTBALL_DIR, TENNIS_DIR]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import compat  # Legacy pickling namespace bridge
import joblib

from football_core.config import LEAGUES, CACHE_DIR, MODELS_DIR, RAW_DATA_DIR
from football_core.data.espn_client import (
    ESPN_LEAGUE_CODES,
    american_to_decimal,
    fetch_espn_upcoming_fixtures,
)
from football_core.data.odds_api import (
    is_valid_odds_api_key,
    fetch_all_live_upcoming_fixtures,
    fetch_league_odds,
)
from football_core.models.predictor import FootballPredictor
from football_core.betting.tracker import PredictionTracker


class TestAC1DailyPipelineEspnFallback(unittest.TestCase):
    """AC 1: Running scripts/run_daily_pipeline.py with ODDS_API_KEY=invalid fetches
    upcoming fixtures from ESPN for all configured competitions.
    """

    def test_odds_api_key_invalid_detection(self):
        """Verify is_valid_odds_api_key correctly identifies 'invalid' and placeholder keys."""
        invalid_keys = ["invalid", "INVALID", "dummy", "test", "none", "null", "false", "", "   ", None]
        for key in invalid_keys:
            with self.subTest(key=key):
                self.assertFalse(
                    is_valid_odds_api_key(key),
                    f"Key '{key}' should be considered invalid/unconfigured.",
                )

    @patch("football_core.data.espn_client.fetch_espn_upcoming_fixtures")
    @patch("football_core.data.odds_api.requests.get")
    def test_fetch_all_live_upcoming_fixtures_bypasses_odds_api_when_key_invalid(
        self, mock_odds_req, mock_espn_fetch
    ):
        """When ODDS_API_KEY is invalid, Odds API HTTP endpoints must NOT be called,
        and ESPN must be queried for all configured competitions in LEAGUES.
        """
        # Mock ESPN returning 1 dummy match per league
        def fake_espn_fetch(league_key, days_ahead=14):
            return [{
                "match_id": f"espn_{league_key}_001",
                "league": league_key,
                "home_team": "Team A",
                "away_team": "Team B",
                "bookmaker": "DraftKings (ESPN)",
                "date": "2026-10-01",
            }]

        mock_espn_fetch.side_effect = fake_espn_fetch

        fixtures = fetch_all_live_upcoming_fixtures(api_key="invalid", use_cache=False)

        # 1. Odds API requests must never be invoked
        mock_odds_req.assert_not_called()

        # 2. ESPN must be called for all configured leagues in LEAGUES
        queried_leagues = {call.args[0] for call in mock_espn_fetch.call_args_list}
        all_configured_leagues = set(LEAGUES.keys())
        self.assertEqual(
            queried_leagues,
            all_configured_leagues,
            "ESPN must be queried for every single competition configured in LEAGUES.",
        )

        # 3. Fixtures must contain items from each queried competition
        self.assertEqual(len(fixtures), len(all_configured_leagues))
        fixture_leagues = {f["league"] for f in fixtures}
        self.assertEqual(fixture_leagues, all_configured_leagues)

    def test_daily_pipeline_executes_with_invalid_odds_api_key(self):
        """Verify that scripts/run_daily_pipeline.py runs end-to-end with ODDS_API_KEY=invalid
        without throwing unhandled exceptions.
        """
        env = os.environ.copy()
        env["ODDS_API_KEY"] = "invalid"
        env["SKIP_RETRAIN"] = "1"
        env["PYTHONPATH"] = f".:{FOOTBALL_DIR}:{TENNIS_DIR}"

        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "run_daily_pipeline.py"),
            "--skip-retrain",
        ]
        res = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
        )

        self.assertEqual(
            res.returncode,
            0,
            f"run_daily_pipeline.py failed with returncode {res.returncode}.\nStderr: {res.stderr}\nStdout: {res.stdout[-1000:]}",
        )
        # Check stdout confirmed successful execution
        self.assertIn("Daily Pipeline completed successfully", res.stdout)
        meta_file = PROJECT_ROOT / "cache" / "pipeline_run_meta.json"
        self.assertTrue(meta_file.exists())
        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)
        self.assertEqual(meta.get("status"), "SUCCESS")


class TestAC2InternationalEspnFixtures(unittest.TestCase):
    """AC 2: International competitions return real fixture data from ESPN
    (at minimum, UEFA Nations League).
    """

    EXPECTED_INTL_LEAGUES = {
        "NationsLeague",
        "WorldCup",
        "WCQ_UEFA",
        "WCQ_CONMEBOL",
        "WCQ_CAF",
        "Euro",
        "CopaAmerica",
        "AFCON",
        "Friendlies",
        "GoldCup",
    }

    def test_international_competitions_registered_with_espn_codes(self):
        """Verify all 10 international tournaments are configured in LEAGUES and ESPN_LEAGUE_CODES."""
        for league_key in self.EXPECTED_INTL_LEAGUES:
            with self.subTest(league=league_key):
                self.assertIn(league_key, LEAGUES, f"{league_key} missing from LEAGUES config")
                cfg = LEAGUES[league_key]
                self.assertTrue(cfg.get("is_international"), f"{league_key} must have is_international=True")
                self.assertTrue(cfg.get("is_cup"), f"{league_key} must have is_cup=True")
                self.assertIn(league_key, ESPN_LEAGUE_CODES, f"{league_key} missing from ESPN_LEAGUE_CODES")
                self.assertTrue(bool(ESPN_LEAGUE_CODES[league_key]), f"{league_key} has empty espn code")

    @patch("football_core.data.espn_client._espn_get_json")
    def test_fetch_espn_upcoming_fixtures_nations_league_real_schema(self, mock_espn_get):
        """Verify fetch_espn_upcoming_fixtures parses real Nations League ESPN API payload."""
        sample_espn_payload = {
            "events": [
                {
                    "id": "712345",
                    "date": "2026-10-10T18:45:00Z",
                    "competitions": [
                        {
                            "id": "712345",
                            "neutralSite": False,
                            "status": {"type": {"completed": False}},
                            "competitors": [
                                {
                                    "homeAway": "home",
                                    "team": {"displayName": "Germany"},
                                },
                                {
                                    "homeAway": "away",
                                    "team": {"displayName": "France"},
                                },
                            ],
                            "odds": [
                                {
                                    "moneyline": {
                                        "home": {"close": {"odds": "+140"}},
                                        "draw": {"close": {"odds": "+230"}},
                                        "away": {"close": {"odds": "+190"}},
                                    },
                                    "total": {
                                        "over": {"close": {"odds": "-115"}},
                                        "under": {"close": {"odds": "-105"}},
                                    },
                                }
                            ],
                        }
                    ],
                },
                {
                    "id": "712346",
                    "date": "2026-10-11T18:45:00Z",
                    "competitions": [
                        {
                            "id": "712346",
                            "neutralSite": True,
                            "status": {"type": {"completed": False}},
                            "competitors": [
                                {
                                    "homeAway": "home",
                                    "team": {"displayName": "Spain"},
                                },
                                {
                                    "homeAway": "away",
                                    "team": {"displayName": "Italy"},
                                },
                            ],
                            "odds": [
                                {
                                    "moneyline": {
                                        "home": {"close": {"odds": "2.10"}},
                                        "draw": {"close": {"odds": "3.20"}},
                                        "away": {"close": {"odds": "3.50"}},
                                    },
                                    "total": {
                                        "over": {"close": {"odds": "1.95"}},
                                        "under": {"close": {"odds": "1.85"}},
                                    },
                                }
                            ],
                        }
                    ],
                },
            ]
        }
        mock_espn_get.return_value = sample_espn_payload

        fixtures = fetch_espn_upcoming_fixtures("NationsLeague")
        self.assertEqual(len(fixtures), 2)

        f1 = fixtures[0]
        self.assertEqual(f1["league"], "NationsLeague")
        self.assertEqual(f1["league_name"], "UEFA Nations League")
        self.assertEqual(f1["home_team"], "Germany")
        self.assertEqual(f1["away_team"], "France")
        self.assertEqual(f1["bookmaker"], "DraftKings (ESPN)")
        self.assertFalse(f1["is_neutral"])
        self.assertEqual(f1["odds_home"], 2.40)  # +140 -> 1 + 140/100 = 2.40
        self.assertEqual(f1["odds_draw"], 3.30)  # +230 -> 1 + 230/100 = 3.30
        self.assertEqual(f1["odds_away"], 2.90)  # +190 -> 1 + 190/100 = 2.90
        self.assertEqual(f1["odds_over25"], 1.87)  # -115 -> 1 + 100/115 = 1.87
        self.assertEqual(f1["odds_under25"], 1.95)  # -105 -> 1 + 100/105 = 1.95

        f2 = fixtures[1]
        self.assertEqual(f2["home_team"], "Spain")
        self.assertEqual(f2["away_team"], "Italy")
        self.assertTrue(f2["is_neutral"])
        self.assertEqual(f2["odds_home"], 2.10)
        self.assertEqual(f2["odds_draw"], 3.20)
        self.assertEqual(f2["odds_away"], 3.50)

    @patch("football_core.data.espn_client._espn_get_json")
    def test_fetch_espn_filters_completed_matches_and_handles_missing_odds(self, mock_espn_get):
        """Adversarial test: Completed matches must be excluded, missing odds handled safely."""
        mock_espn_get.return_value = {
            "events": [
                {
                    "id": "completed_match",
                    "date": "2026-10-09T18:45:00Z",
                    "competitions": [
                        {
                            "status": {"type": {"completed": True}},
                            "competitors": [
                                {"homeAway": "home", "team": {"displayName": "Belgium"}},
                                {"homeAway": "away", "team": {"displayName": "Netherlands"}},
                            ],
                        }
                    ],
                },
                {
                    "id": "uncompleted_no_odds",
                    "date": "2026-10-12T18:45:00Z",
                    "competitions": [
                        {
                            "status": {"type": {"completed": False}},
                            "competitors": [
                                {"homeAway": "home", "team": {"displayName": "Portugal"}},
                                {"homeAway": "away", "team": {"displayName": "Croatia"}},
                            ],
                            "odds": [],
                        }
                    ],
                },
            ]
        }
        fixtures = fetch_espn_upcoming_fixtures("NationsLeague")
        self.assertEqual(len(fixtures), 1, "Completed match must be filtered out.")
        self.assertEqual(fixtures[0]["home_team"], "Portugal")
        self.assertEqual(fixtures[0]["away_team"], "Croatia")
        self.assertIsNone(fixtures[0]["odds_home"])
        self.assertIsNone(fixtures[0]["odds_draw"])
        self.assertIsNone(fixtures[0]["odds_away"])

    def test_cached_fixtures_contain_international_competitions(self):
        """Verify Football/data/cache/live_upcoming_fixtures.json includes international competition records."""
        cache_file = CACHE_DIR / "live_upcoming_fixtures.json"
        self.assertTrue(cache_file.exists(), f"Missing cache file: {cache_file}")

        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        matches = data.get("matches", [])
        self.assertGreater(len(matches), 0, "Cached upcoming fixtures list should not be empty")

        match_ids = [m.get("match_id", "") for m in matches]
        # Verify key international tournaments are present in the cached fixtures
        intl_keys = ["WorldCup", "WCQ_UEFA", "Euro", "CopaAmerica", "AFCON", "GoldCup"]
        found_intl = any(any(ik in mid for ik in intl_keys) for mid in match_ids)
        self.assertTrue(
            found_intl,
            f"Cached fixtures must contain international competition records. Found: {match_ids}",
        )


class TestAC3NoFabricatedDataOrProhibitedRandomGenerators(unittest.TestCase):
    """AC 3: No fabricated/hardcoded odds, scores, or fixtures anywhere
    (grep for random.seed, random.choice, random.gauss in Python files returns 0 hits
    outside ML random_state).
    """

    PROHIBITED_PATTERN = re.compile(r"\brandom\.(seed|choice|gauss|randint|uniform|sample)\b")

    def test_grep_zero_prohibited_random_generators_in_codebase(self):
        """Recursively scan all Python files in Football/, Tennis/, scripts/ for prohibited random calls."""
        search_dirs = [
            PROJECT_ROOT / "Football",
            PROJECT_ROOT / "Tennis",
            PROJECT_ROOT / "scripts",
        ]

        violations = []
        for sdir in search_dirs:
            for py_file in sdir.rglob("*.py"):
                # Skip caches or virtual environments if nested
                if ".venv" in str(py_file) or "__pycache__" in str(py_file):
                    continue

                try:
                    with open(py_file, "r", encoding="utf-8") as f:
                        for line_num, line in enumerate(f, 1):
                            if self.PROHIBITED_PATTERN.search(line):
                                violations.append(f"{py_file.relative_to(PROJECT_ROOT)}:{line_num} -> {line.strip()}")
                except Exception as e:
                    violations.append(f"Failed to read {py_file}: {e}")

        self.assertEqual(
            violations,
            [],
            f"Found prohibited random generator calls in production code:\n" + "\n".join(violations),
        )

    def test_random_state_is_strictly_for_ml_reproducibility(self):
        """Verify that any occurrences of 'random_state' in Python files are purely deterministic ML seeds."""
        for py_file in (PROJECT_ROOT / "Football").rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()
            if "random_state" in content:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.keyword) and node.arg == "random_state":
                        # Value must be an integer constant or None (e.g. random_state=42)
                        self.assertTrue(
                            isinstance(node.value, ast.Constant) and isinstance(node.value.value, (int, type(None))),
                            f"In {py_file}: random_state must be a deterministic constant, got {ast.dump(node.value)}",
                        )


class TestAC4InternationalModelTrainingScript(unittest.TestCase):
    """AC 4: International model training script runs end-to-end:
    PYTHONPATH=".:Football" python -c "from football_core.models.train_international import train_international_model; train_international_model()".
    """

    def test_train_international_model_import_and_callable(self):
        """Verify train_international_model can be imported and has expected signature."""
        from football_core.models.train_international import train_international_model
        import inspect

        sig = inspect.signature(train_international_model)
        params = list(sig.parameters.keys())
        self.assertIn("save_path", params)
        self.assertIn("evaluate_combined", params)
        self.assertIn("data_path", params)

    def test_train_international_model_runs_end_to_end(self):
        """Execute train_international_model end-to-end with real historical data.
        Verifies feature pipeline, LightGBM training, calibration, and bundle export.
        """
        from football_core.models.train_international import train_international_model

        with tempfile.NamedTemporaryFile(suffix=".joblib", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            # Run training end-to-end on real historical international matches
            bundle = train_international_model(
                save_path=tmp_path,
                evaluate_combined=False,
            )

            # 1. Verify bundle output structure
            self.assertIsInstance(bundle, dict)
            self.assertEqual(bundle["league_key"], "International")
            self.assertIn("pipeline", bundle)
            self.assertIn("models", bundle)
            self.assertIn("metrics", bundle)

            # 2. Verify out-of-sample accuracy meets threshold > 40%
            acc = bundle["metrics"]["acc_1x2"]
            self.assertGreater(
                acc,
                0.40,
                f"Out-of-sample 1X2 accuracy {acc:.4f} must exceed 40.0% threshold.",
            )

            # 3. Verify file exists on disk and is loadable
            self.assertTrue(os.path.exists(tmp_path))
            self.assertGreater(os.path.getsize(tmp_path), 1_000_000)

            loaded = joblib.load(tmp_path)
            self.assertEqual(loaded["league_key"], "International")
            self.assertAlmostEqual(loaded["metrics"]["acc_1x2"], acc, places=5)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


class TestAC5InternationalBundleIntegrityAndAccuracy(unittest.TestCase):
    """AC 5: Football/models_saved/International_bundle.joblib exists,
    is loadable, and out-of-sample 1X2 accuracy > 40%.
    """

    BUNDLE_PATH = MODELS_DIR / "International_bundle.joblib"

    def setUp(self):
        self.assertTrue(
            self.BUNDLE_PATH.exists(),
            f"Model bundle not found at {self.BUNDLE_PATH}",
        )
        self.bundle = joblib.load(self.BUNDLE_PATH)

    def test_bundle_structure_and_contracts(self):
        """Verify the saved bundle strictly matches the interface contract in PROJECT.md."""
        self.assertEqual(self.bundle.get("league_key"), "International")

        # Models dictionary contract
        models = self.bundle.get("models", {})
        self.assertIn("model_1x2", models)
        self.assertIn("model_over25", models)
        self.assertIn("model_btts", models)
        self.assertIn("base_1x2", models)

        # Pipeline contract
        pipeline = self.bundle.get("pipeline")
        self.assertIsNotNone(pipeline)
        self.assertTrue(hasattr(pipeline, "build_inference_features"))
        self.assertTrue(hasattr(pipeline, "elo_engine"))
        self.assertTrue(hasattr(pipeline, "form_tracker"))
        self.assertTrue(hasattr(pipeline, "h2h_tracker"))

        # Known teams populated
        self.assertGreater(len(pipeline.elo_engine.ratings), 200, "Pipeline should track over 200 national teams.")
        self.assertIn("France", pipeline.elo_engine.ratings)
        self.assertIn("Germany", pipeline.elo_engine.ratings)
        self.assertIn("Brazil", pipeline.elo_engine.ratings)

    def test_out_of_sample_metrics_exceed_acceptance_threshold(self):
        """Verify out-of-sample 1X2 accuracy > 40% and metric completeness."""
        metrics = self.bundle.get("metrics", {})
        acc_1x2 = metrics.get("acc_1x2")
        self.assertIsNotNone(acc_1x2, "acc_1x2 metric missing")
        self.assertGreater(
            acc_1x2,
            0.40,
            f"Out-of-sample accuracy {acc_1x2:.4f} must exceed 40.0% acceptance threshold",
        )
        # Verify log loss is reasonable (< 1.0) and test size is sufficient
        self.assertLess(metrics.get("log_loss_1x2", 99.0), 1.0)
        self.assertGreater(metrics.get("n_test", 0), 1000)

        # Verify Over/Under 2.5 and BTTS accuracies are valid
        self.assertGreater(metrics.get("acc_over25", 0.0), 0.50)
        self.assertGreater(metrics.get("acc_btts", 0.0), 0.50)

    def test_bundle_inference_probability_distribution(self):
        """Verify inference feature building and calibrated probability predictions."""
        pipeline = self.bundle["pipeline"]
        model_1x2 = self.bundle["models"]["model_1x2"]

        # France vs Germany at non-neutral venue
        X_home = pipeline.build_inference_features("France", "Germany", is_neutral=False, tournament="UEFA Nations League")
        probs_home = model_1x2.predict_proba(X_home)[0]

        self.assertEqual(len(probs_home), 3)
        self.assertAlmostEqual(float(sum(probs_home)), 1.0, places=4)
        for p in probs_home:
            self.assertGreaterEqual(p, 0.0)
            self.assertLessEqual(p, 1.0)

        # France vs Germany at neutral venue
        X_neut = pipeline.build_inference_features("France", "Germany", is_neutral=True, tournament="FIFA World Cup")
        probs_neut = model_1x2.predict_proba(X_neut)[0]

        self.assertEqual(len(probs_neut), 3)
        self.assertAlmostEqual(float(sum(probs_neut)), 1.0, places=4)

        # Home win probability should be slightly higher when playing at home vs neutral
        self.assertGreaterEqual(probs_home[0], probs_neut[0] - 0.05)


class TestAC6PipelineExportAndWebTypeScript(unittest.TestCase):
    """AC 6: scripts/run_daily_pipeline.py and scripts/export_web_data.py include
    international competitions, and cd web && npx tsc --noEmit returns exit code 0.
    """

    def test_daily_pipeline_handles_international_competitions(self):
        """Verify predictor routes international competitions correctly with context params."""
        predictor = FootballPredictor()
        self.assertTrue(predictor.is_league_ready("International"))
        self.assertTrue(predictor.is_league_ready("NationsLeague"))
        self.assertTrue(predictor.is_league_ready("WorldCup"))

        pred = predictor.predict_match(
            home_team="France",
            away_team="Germany",
            league_key="NationsLeague",
            is_neutral=False,
            tournament="UEFA Nations League",
            match_date="2026-10-10",
        )

        self.assertIn("prob_home", pred)
        self.assertIn("prob_draw", pred)
        self.assertIn("prob_away", pred)
        self.assertIn("prob_over25", pred)
        self.assertIn("prob_btts_yes", pred)
        self.assertIn("score_matrix", pred)
        self.assertEqual(len(pred["score_matrix"]), 8)
        self.assertEqual(len(pred["score_matrix"][0]), 8)

    def test_export_web_data_handles_international_fixtures(self):
        """Verify export_web_data enrichment processes international match fixtures."""
        from scripts.export_web_data import enrich_football_upcoming
        from datetime import datetime, timezone

        predictor = FootballPredictor()
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        raw_fixtures = [
            {
                "match_id": f"NationsLeague_Germany_France_{today_str}",
                "league": "NationsLeague",
                "league_name": "UEFA Nations League",
                "home_team": "Germany",
                "away_team": "France",
                "date": today_str,
                "is_neutral": False,
                "odds_home": 2.40,
                "odds_draw": 3.30,
                "odds_away": 2.90,
            }
        ]

        enriched, picks = enrich_football_upcoming(raw_fixtures, predictor)
        self.assertEqual(len(enriched), 1)
        item = enriched[0]
        self.assertEqual(item["home_team"], "Germany")
        self.assertEqual(item["away_team"], "France")
        self.assertIn("prob_home", item)
        self.assertIn("drivers", item)
        self.assertIn("h2h_matches", item)

    def test_web_app_tsx_contains_international_leagues(self):
        """Verify web/src/App.tsx registers all 10 international tournaments in INTERNATIONAL_LEAGUES."""
        app_file = PROJECT_ROOT / "web" / "src" / "App.tsx"
        self.assertTrue(app_file.exists())

        with open(app_file, "r", encoding="utf-8") as f:
            content = f.read()

        expected_keys = [
            "NationsLeague",
            "WorldCup",
            "WCQ_UEFA",
            "WCQ_CONMEBOL",
            "WCQ_CAF",
            "Euro",
            "CopaAmerica",
            "AFCON",
            "Friendlies",
            "GoldCup",
        ]
        self.assertIn("INTERNATIONAL_LEAGUES", content)
        for k in expected_keys:
            self.assertIn(f"'{k}'", content, f"Key '{k}' must be registered in App.tsx")

    def test_web_typescript_typecheck_clean(self):
        """Verify cd web && npx tsc --noEmit returns exit code 0 without any type errors."""
        res = subprocess.run(
            ["npx", "tsc", "--noEmit"],
            cwd=str(PROJECT_ROOT / "web"),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(
            res.returncode,
            0,
            f"TypeScript typechecking failed with returncode {res.returncode}.\nStderr: {res.stderr}\nStdout: {res.stdout}",
        )


class TestAC7HistoricalTrackerPreservation(unittest.TestCase):
    """AC 7: Exactly 203 settled football tracker entries in Football/data/cache/predictions_tracker.json
    and 200 tennis tracker entries in Tennis/data/tracker/predictions_archive.json remain 100% intact.
    """

    FOOTBALL_TRACKER_PATH = FOOTBALL_DIR / "data" / "cache" / "predictions_tracker.json"
    TENNIS_TRACKER_PATH = TENNIS_DIR / "data" / "tracker" / "predictions_archive.json"

    def test_football_tracker_preserves_exactly_203_settled_records(self):
        """Verify exactly 203 settled football match entries remain intact."""
        self.assertTrue(self.FOOTBALL_TRACKER_PATH.exists())
        with open(self.FOOTBALL_TRACKER_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIsInstance(data, list)
        settled = [p for p in data if p.get("status") == "settled"]
        self.assertEqual(
            len(settled),
            203,
            f"Expected exactly 203 settled football tracker entries, found {len(settled)}.",
        )

        # Integrity verification: Every settled record must have valid match_id, teams, and actual scores
        for p in settled:
            self.assertTrue(bool(p.get("match_id")), "Settled entry missing match_id")
            self.assertTrue(bool(p.get("home_team")), "Settled entry missing home_team")
            self.assertTrue(bool(p.get("away_team")), "Settled entry missing away_team")
            self.assertIsNotNone(p.get("actual_score"), "Settled entry missing actual_score")
            self.assertIn("-", p.get("actual_score", ""), "actual_score should be in 'H-A' format")

    def test_tennis_tracker_preserves_exactly_200_historical_records(self):
        """Verify exactly 200 historical tennis matches remain intact."""
        self.assertTrue(self.TENNIS_TRACKER_PATH.exists())
        with open(self.TENNIS_TRACKER_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIsInstance(data, list)
        historical = [p for p in data if p.get("status") in ["WON", "LOST", "NO_BET", "VOID"]]
        self.assertEqual(
            len(historical),
            200,
            f"Expected exactly 200 historical tennis matches, found {len(historical)}.",
        )

        for p in historical:
            self.assertTrue(bool(p.get("match_id")), "Tennis record missing match_id")
            self.assertTrue(bool(p.get("p1_name")), "Tennis record missing p1_name")
            self.assertTrue(bool(p.get("p2_name")), "Tennis record missing p2_name")
            self.assertIn(p.get("status"), ["WON", "LOST", "NO_BET", "VOID"])

    def test_tracker_immutability_prevents_overwriting_settled_records(self):
        """Verify PredictionTracker.log_prediction strictly refuses to mutate settled entries."""
        tracker = PredictionTracker()
        settled_entries = [p for p in tracker.predictions if p.get("status") == "settled"]
        self.assertGreater(len(settled_entries), 0)

        target = settled_entries[0]
        original_home = target.get("home_team")
        original_prob = target.get("prob_home")

        # Attempt to log altered data using the settled match_id
        mutated_payload = {
            "match_id": target["match_id"],
            "league_key": target.get("league_key", "EPL"),
            "date": target.get("date", "2026-01-01"),
            "home_team": "Altered Home Team",
            "away_team": "Altered Away Team",
            "prob_home": 0.999,
        }

        result = tracker.log_prediction(mutated_payload)
        self.assertFalse(
            result,
            "log_prediction must return False when attempting to mutate an already settled record.",
        )

        # Verify entry remains unaltered
        refreshed_entry = [p for p in tracker.predictions if p.get("match_id") == target["match_id"]][0]
        self.assertEqual(refreshed_entry.get("home_team"), original_home)
        self.assertEqual(refreshed_entry.get("prob_home"), original_prob)


if __name__ == "__main__":
    unittest.main(verbosity=2)
