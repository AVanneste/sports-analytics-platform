# Project: Sports Analytics Platform — Free Data Sources & International Football

## Architecture
The platform is a hybrid Python/TypeScript sports analytics system covering domestic football, European club competitions, ATP/WTA tennis, and international football competitions.

- **Data Tier (`Football/football_core/data/`)**:
  - `espn_client.py`: Free primary data source for upcoming fixtures, scoreboards, boxscores, and DraftKings consensus odds (1X2, Over/Under 2.5).
  - `odds_api.py`: Optional multi-bookmaker odds provider. Automatically bypassed when exhausted or with invalid keys.
  - `api_football.py`: Secondary source for detailed match statistics during reconciliation.
- **Model Tier (`Football/football_core/models/`)**:
  - Domestic models: League-specific LightGBM + CalibratedClassifierCV bundles in `Football/models_saved/`.
  - International model: `International_bundle.joblib` trained on real historical international match results (1872–2026), incorporating national team Elo ratings (with neutral venue adjustments), tournament importance weights, rolling form, and H2H statistics.
  - `predictor.py`: Unified inference engine (`FootballPredictor`) dynamically routing domestic vs cup vs international competitions.
- **Tracking & Betting Tier (`Football/football_core/betting/`)**:
  - `tracker.py`: Logs predictions, reconciles completed results, maintains ledger. Immutable settled records.
- **Automation & Export Tier (`scripts/`)**:
  - `run_daily_pipeline.py`: Daily batch orchestrator (fetch fixtures → predict → track → reconcile → retrain domestic → export).
  - `export_web_data.py`: Transforms tracker and upcoming predictions into web frontend payload `web/public/data/sports_data.json`.
- **Presentation Tier (`web/`)**:
  - React, Vite, Tailwind CSS, TypeScript frontend consuming `sports_data.json`.

---

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | ESPN Primary Fixtures & Odds | Fetch fixtures and DraftKings consensus odds across domestic and international competitions via ESPN API | M1 | Survey / R1 |
| 2 | Odds API Quota & Fallback Hardening | Seamless fallback to ESPN when Odds API quota exhausted or `ODDS_API_KEY=invalid`, zero delays | M1 | Survey / R1 |
| 3 | International Competition Config | Register 10 international competitions in `LEAGUES` with metadata (`is_cup: True`, `is_international: True`, flags, codes) | M1 | Survey / R2 |
| 4 | Team Name Normalization | Map ESPN team names to canonical dataset names in `helpers.py` | M1 | Survey / R2 |
| 5 | International Feature Pipeline | National team Elo (initialized from 1872), neutral venue flag, tournament weights, rolling form, H2H | M2 | Survey / R3 |
| 6 | International Model Training Script | Train separate LightGBM + CalibratedClassifierCV model on real data, achieve > 40% out-of-sample accuracy, save `International_bundle.joblib` | M2 | Survey / R3 |
| 7 | Predictor International Routing | Update `FootballPredictor` to load `International_bundle.joblib` and route international predictions | M3 | Survey / R3 |
| 8 | Tracker Compatibility Fix | Add `log_prediction` method to `PredictionTracker` ensuring compatibility with daily pipeline | M3 | Survey / R4 |
| 9 | Daily Pipeline International Integration | Integrate international competitions into `run_daily_pipeline.py` fetch-predict-track cycle without domestic regressions | M3 | Survey / R4 |
| 10 | Web Export of International Fixtures | Export international fixtures, predictions, and tracker data in `export_web_data.py` | M3 | Survey / R4 |
| 11 | Web UI League Display & Filters | Support international competitions in React frontend with clean TypeScript build (`tsc --noEmit`) | M3 | Survey / R4 |
| 12 | Zero Regression & Tracker Preservation | Preserve 203 settled football tracker entries and 200 tennis tracker entries intact | M4 | Survey / AC |
| 13 | Anti-Hallucination & Acceptance Gating | Verify 0 fake data generators, verify out-of-sample accuracy > 40%, verify ESPN fallback under `ODDS_API_KEY=invalid` | M4 | Survey / AC |

---

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Data Source Integration & League Config | `config.py`, `espn_client.py`, `odds_api.py`, `helpers.py` | None | DONE |
| 2 | International Football ML Model | `international_features.py`, `train_international.py`, `International_bundle.joblib` | M1 | DONE |
| 3 | Pipeline & Web Dashboard Integration | `predictor.py`, `tracker.py`, `run_daily_pipeline.py`, `export_web_data.py`, `web/` | M1, M2 | DONE |
| 4 | E2E Acceptance Testing & Adversarial Hardening | Comprehensive test suite (Tiers 1-4), regression verification, audit | M1, M2, M3 | DONE |

---

## Interface Contracts

### 1. `config.py` ↔ Data Clients & Pipeline
- `LEAGUES[league_key]`:
  ```python
  {
      "name": str,               # e.g., "UEFA Nations League"
      "country": str,            # "Europe" or confederation/global
      "code": str,               # "UNL"
      "odds_key": Optional[str], # None for competitions not in The Odds API
      "espn_code": str,          # "uefa.nations"
      "flag": str,               # "🇪🇺"
      "is_cup": True,            # Bypasses domestic CSV downloader
      "is_international": True,  # Flags international national-team match
  }
  ```

### 2. `espn_client.py` ↔ Upcoming Fixture Consumers
- `fetch_espn_upcoming_fixtures(league_key: str, days_ahead: int = 14) -> List[Dict[str, Any]]`:
  Returns list of dicts:
  - `match_id`: `f"espn_{event_id}"`
  - `date`: ISO string `YYYY-MM-DDTHH:MM:SSZ`
  - `league`: league_key
  - `league_name`: human readable name
  - `flag`: flag emoji
  - `home_team`: canonical home team name
  - `away_team`: canonical away team name
  - `odds_home`, `odds_draw`, `odds_away`: float decimal odds or None
  - `odds_over25`, `odds_under25`: float decimal odds or None
  - `bookmaker`: "DraftKings (ESPN)"
  - `is_neutral`: bool

### 3. `train_international.py` ↔ `International_bundle.joblib`
- Entry point: `train_international_model(save_path: Optional[str] = None) -> Dict[str, Any]`
- Bundle format:
  ```python
  {
      "league_key": "International",
      "pipeline": InternationalFeaturePipeline,
      "models": {
          "model_1x2": CalibratedClassifierCV,
          "model_over25": CalibratedClassifierCV,
          "model_btts": CalibratedClassifierCV,
          "base_1x2": LGBMClassifier,
      },
      "metrics": {
          "accuracy_1x2": float,  # Must be > 0.40
          "log_loss_1x2": float,
          "accuracy_over25": float,
          "test_size": int,
      }
  }
  ```

### 4. `tracker.py` ↔ `run_daily_pipeline.py`
- `PredictionTracker.log_prediction(pred_item: Dict[str, Any]) -> bool`:
  - Accepts top-level `match_id`, `date`, `league_key`, `home_team`, `away_team`, `predicted_winner`, `probabilities`, `odds`, etc.
  - Normalizes and delegates to `log_full_match_prediction`.
  - Guarantees already settled entries (`status == "settled"`) are never overwritten.

---

## Code Layout
- `Football/football_core/config.py`: League definitions and global constants.
- `Football/football_core/data/espn_client.py`: ESPN API fixtures, scoreboards, and odds parsing.
- `Football/football_core/data/odds_api.py`: The Odds API client with quota fallback to ESPN.
- `Football/football_core/utils/helpers.py`: Team name normalization dictionaries and utility functions.
- `Football/football_core/models/international_features.py`: International feature engineering (Elo, H2H, form, tournament weights).
- `Football/football_core/models/train_international.py`: International model training pipeline and bundle exporter.
- `Football/models_saved/International_bundle.joblib`: Serialized international model bundle.
- `Football/football_core/models/predictor.py`: Prediction engine with international model routing.
- `Football/football_core/betting/tracker.py`: Prediction ledger and reconciliation manager.
- `scripts/run_daily_pipeline.py`: Scheduled batch execution script.
- `scripts/export_web_data.py`: Web dashboard data exporter.
- `web/src/App.tsx`: Web application root and league filtering.
- `web/public/data/sports_data.json`: Static JSON data consumed by the frontend.
