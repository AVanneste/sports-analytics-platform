# OmniVision Sports: football & tennis prediction engine

Outcome models for European football (9 domestic leagues, European cups, internationals) and
ATP/WTA tennis, a daily data pipeline that logs every prediction to an append-only ledger and
grades it against official results, and a React dashboard built from the pipeline's JSON export.

## Current performance (read this first)

The pipeline measures every model against the bookmaker's vig-free price on the same matches
(`python scripts/evaluate.py`). As of October 2026:

* **No model beats the market.** On chronological holdout data every football league trails the
  market by 0.005–0.025 log loss (1X2) and both tennis tours by ~0.03.
* **The old value-bet rule lost money.** Live ledger: football 78 bets at −42% ROI while the model
  claimed +25% EV; tennis 103 bets at −14% while claiming +32%. Backtested on held-out seasons with
  real Bet365 prices it also loses (e.g. ATP −2% over 894 bets claimed at +35% EV).
* Predictions are therefore **shrunk toward the market price** with a weight fitted on validation
  data; where that weight is 0 the model adds nothing and no pick is made. Treat any remaining
  "model edge" as unproven until the closing-line value (CLV) in the report turns positive.

## How it works

```
football-data.co.uk / tennis-data.co.uk / Sackmann ──► features (Elo, Dixon-Coles, form, H2H,
ESPN fixtures + odds (The Odds API optional)            referee, serve/return) ──► calibrated
                                                        LightGBM ──► blend with market price
                                                                         │
            React dashboard ◄── web/public/data/sports_data.json ◄── ledgers + evaluation report
```

| Path | What lives there |
|---|---|
| `sports_common/` | Shared: secrets lookup + log redaction, crash-safe JSON ledgers, betting maths, model-vs-market evaluation, promotion gate |
| `Football/football_core/` | Data clients (football-data, ESPN, The Odds API, API-Football), features, models, ledger |
| `Tennis/tennis_core/` | Same for tennis (tennis-data.co.uk, Sackmann serve/return stats, ESPN) |
| `scripts/run_daily_pipeline.py` | Daily job: refresh data → retrain if due → predict & log → reconcile results → export |
| `scripts/evaluate.py` | Read-only report: model vs market, ROI vs claimed EV, CLV, holdout metrics |
| `scripts/export_web_data.py` | Builds the dashboard payload (reads ledgers, never writes them) |
| `web/` | React + Vite + Tailwind dashboard |
| `tests/` | Offline test suite (`pytest`); `pytest -m e2e` runs the legacy network-bound checks |

### Training and promotion

* Chronological split: fit on the first 70% of matches, choose blend weights (ML vs Dixon-Coles,
  model vs market) on the next 15%, report on the last 15%, then refit on everything.
* Features use only information available before each match; `tests/test_training.py` checks this
  by truncating all data sources and asserting earlier features do not change.
* A retrained classifier replaces the deployed one only if its holdout skill against the market is
  not worse. The feature state (ratings, form) is always refreshed.

### Ledgers

* `Football/data/cache/predictions_tracker.json` and `Tennis/data/tracker/predictions_archive.json`.
* Writes are atomic with a daily backup in `backups/` next to each file; a corrupt ledger stops the
  pipeline instead of being replaced.
* Settled records are immutable. Opening odds and the first value pick are frozen at the first log;
  the latest pre-match prices are kept for CLV.
* Football probabilities are fractions; tennis probabilities, EV and edge are stored in percent.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"            # project + exactly pinned dependencies (see pyproject.toml)
python -m pytest                   # offline tests
cd web && npm ci && npm run dev    # dashboard at http://localhost:3000
```

API keys are optional; without them the free ESPN / tennis-data.co.uk sources are used. Put them in
`.env` at the repository root (never in code):

```
ODDS_API_KEY=...
API_FOOTBALL_KEY=...
GEMINI_API_KEY=...
```

For the scheduled GitHub Action, add the same names as repository secrets.

## Running

```bash
python scripts/run_daily_pipeline.py      # full daily run (what CI does)
python scripts/evaluate.py                # honest performance report
python Football/run_pipeline.py --all     # manual full football retrain
python Tennis/run_pipeline.py --all       # manual full tennis retrain
```

Daily automation (`.github/workflows/daily_update.yml`, 04:37 UTC) commits the updated ledgers,
data, payload and, on retrain days, models. Retraining happens weekly (`RETRAIN_WEEKDAY`, default
Monday UTC), when forced (`FORCE_RETRAIN=1` or `--force-retrain`), or when a deployed model is
missing, stale or from an older feature schema; `SKIP_RETRAIN=1` disables it. Between retrains the
feature state is rebuilt in memory, so no model files change.

## Known data issues

* **tennis-data.co.uk** currently returns 404 for the 2025 and 2026 files, so the tennis models
  stop at November 2025. The downloader no longer saves error pages as data.
* The **Sackmann** mirror used for serve/return stats stops in May 2026.
* **ClubElo** (a cross-league club rating) was unreachable, so European cup ties between leagues
  use non-comparable ratings and are flagged low confidence (never value picks).
* Internationals have no historical prices, so their model has never been validated against the
  market and produces no value picks.

## Deprecated

The Streamlit app (`app.py`, `streamlit_app.py`, `Football/football_app/`, `Tennis/tennis_app/`) is
superseded by the React dashboard and is due to be removed.
