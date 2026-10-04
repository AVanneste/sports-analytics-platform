# OmniVision Sports: football & tennis prediction engine

Outcome models for European football (9 domestic leagues, European cups, internationals) and
ATP/WTA tennis, a daily data pipeline that logs every prediction to an append-only ledger and
grades it against official results, and a React dashboard built from the pipeline's JSON export.

## Current performance (read this first)

The pipeline measures every model against the bookmaker's vig-free price on the same matches
(`python scripts/evaluate.py`). As of October 2026:

* **No model beats the market.** In the walk-forward backtest (July 2024 onwards) the football
  models trail the closing price by 0.018 log loss on 1X2, and the tennis models trail Bet365 by
  0.015 (0.03 before the October 2026 fixes).
* **The old value-bet rule lost money.** Live ledger: football 78 bets at −42% ROI while the model
  claimed +25% EV; tennis 103 bets at −14% while claiming +32%. Backtested on held-out seasons with
  real Bet365 prices it also loses (e.g. ATP −2% over 894 bets claimed at +35% EV).
* Predictions are therefore **shrunk toward the market price** with a weight fitted on validation
  data; where that weight is 0 the model adds nothing and no pick is made. Treat any remaining
  "model edge" as unproven until the closing-line value (CLV) in the report turns positive.

## How it works

```
football-data.co.uk, Understat xG        ──► features (Elo, Dixon-Coles on goals + shots + xG,
tennis-data.co.uk, Sackmann                    form, H2H, referee, serve/return) ──► calibrated
ESPN fixtures + odds (The Odds API optional)   LightGBM blended with Dixon-Coles; corners & cards
                                               count models ──► blend with market price
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
| `scripts/backtest.py` | Walk-forward accuracy backtest of the football models on every market (see below) |
| `scripts/tune_model.py` | Walk-forward tuning of the goal, corners and cards models, confirmed on unseen seasons |
| `scripts/backtest_tennis.py`, `scripts/tune_tennis_elo.py` | The same for the tennis match-winner models and Elo ratings |
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

### Measuring accuracy

`scripts/backtest.py` replays every domestic league walk-forward. Each model is refitted on the
matches before each monthly cut-off (quarterly for the LightGBM stack) and predicts only the next
window. Every market is scored with log loss, Brier score, ranked probability score (1X2),
accuracy and calibration error, plus paired per-match differences with standard errors.
Bookmaker opening and closing prices are scored the same way, as a yardstick only: no model uses
odds as an input.

`scripts/tune_model.py --target goals|corners|cards` searches settings on 2022/23–2023/24 and
then compares the winner with the current defaults on 2024/25 onwards. Settings are adopted only
if they win on those unseen seasons.

```bash
python scripts/backtest.py --from 2024-07-01                    # every model, every domestic league
python scripts/backtest.py --leagues EPL --models dixon_coles stacked production props_count
python scripts/tune_model.py --target cards
```

Log loss on the unseen 2024/25+ seasons (9 leagues, 6,287 matches; lower is better):

| Market | League base rate | Before (main) | Now | Bookmaker closing price |
|---|---|---|---|---|
| 1X2 | 1.0761 | 0.9851 | **0.9833** | 0.9650 |
| Over/Under 2.5 | 0.6863 | 0.6790 | **0.6760** | 0.6682 |
| Both teams to score | 0.6882 | 0.6874 | **0.6860** | – |
| Exact score (Dixon-Coles) | 3.0723 | 2.9229 | **2.9089** | – |
| Corners over 9.5 | 0.6887 | 0.6903 | **0.6828** | – |
| Cards over 3.5 | 0.6741 | 0.6760 | **0.6626** | – |

What moved the numbers:
- **Goals:** time decay, shrinkage and a shots-on-target signal were tuned walk-forward.
- **xG:** Understat expected goals feed the top five leagues.
- **Promoted teams:** they now start below the league average.
- **Corners and cards:** heavily shrunk team count models (with a referee factor for cards)
  replaced the heuristics.

LightGBM now adds almost nothing on top of Dixon-Coles: its blend weights are small, and 1X2 log
loss is the same with or without it. A Dixon-Coles + Elo stacker was tested and not adopted.
The bookmaker closing price is still clearly better, by 0.018 on 1X2.

Tennis match winner, both tours, July 2024 onwards (11,646 matches):

| Model | Log loss | Accuracy |
|---|---|---|
| Ranking only | 0.6309 | 63.6% |
| Tuned Elo alone | 0.6204 | 64.9% |
| Deployed before (history from 2023) | 0.6218 | 64.7% |
| **Now** (history from 2014, trained from 2018) | **0.6054** | **66.5%** |
| Bet365 price (yardstick) | 0.5908 | 68.0% |

Most of the tennis gain comes from a longer history: building ratings and form from 2014 instead
of 2023. Two things were measured and left out because they add nothing to LightGBM: a tuned Elo
feature, and the Sackmann serve/return stats.

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
```

For the scheduled GitHub Action, add the same names as repository secrets.

## Running

```bash
python scripts/run_daily_pipeline.py      # full daily run (what CI does)
python scripts/evaluate.py                # honest performance report
python Football/run_pipeline.py --all     # manual full football retrain
python Tennis/run_pipeline.py --all       # manual full tennis retrain
```

Daily automation (`.github/workflows/daily_update.yml`) commits the updated ledgers, data, payload
and, on retrain days, models. It is triggered at 05:00 UTC by an external scheduler (cron-job.org
calling GitHub's workflow_dispatch API with a token limited to this repo's Actions). GitHub's own
schedule (00:37 UTC, which GitHub starts hours late) is only a backup. A run skips itself when
today's run already succeeded; use "Run workflow" with *force* to run again.

Retraining happens weekly (`RETRAIN_WEEKDAY`, default Monday UTC), when forced (`FORCE_RETRAIN=1` or `--force-retrain`), or when a deployed model is
missing, stale or from an older feature schema; `SKIP_RETRAIN=1` disables it. Between retrains the
feature state is rebuilt in memory, so no model files change.

## Known data issues

* The **Sackmann** mirror used for serve/return stats stops in May 2026 and has no WTA data. Walk-forward,
  those stats add nothing measurable to the match-winner model.
* **ClubElo** (a cross-league club rating) was unreachable, so European cup ties between leagues
  use non-comparable ratings and are flagged low confidence (never value picks).
* Internationals have no historical prices, so their model has never been validated against the
  market and produces no value picks.
