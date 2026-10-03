# Project: engineering contracts and invariants

User-facing documentation (setup, running, current performance) lives in `README.md`. This file
records the contracts the code relies on, for anyone (or any agent) changing it.

## Invariants

1. **No lookahead.** Every training feature for a match uses only information available before it.
   Enforced by `tests/test_training.py::test_tennis_features_do_not_depend_on_future_matches` and
   the football train/serve consistency test. Sackmann rows count only once their tournament
   started 14+ days before the match.
2. **Market is the baseline.** Models are judged by log loss against the vig-free bookmaker price
   on the same matches (`sports_common.evaluation.compare_to_market`), never by accuracy alone.
3. **No invented data.** Missing statistics stay missing (None/NaN); unknown values are never
   replaced by plausible constants in features, targets, ledgers or the UI.
4. **Ledgers are append-only.** Settled/graded records are never modified (only derived fields such
   as Kelly PnL may be backfilled by `upgrade_ledger`). The tracker classes are the only writers;
   writes are atomic with daily backups; a corrupt file raises `LedgerCorruptError`.
5. **No secrets in code.** Keys come from the environment / `.env` via `sports_common.secrets`;
   logs pass through `RedactingFormatter`.

## Model bundle contract (football)

`Football/models_saved/<League>_bundle.joblib` (joblib, compress=3):

```python
{
    "league_key": str,
    "pipeline": FootballFeaturePipeline,      # feature state; schema_version == FEATURE_SCHEMA_VERSION
    "models": {"model_1x2", "model_over25", "model_btts", "base_1x2"},
    "metrics": {
        "schema_version", "trained_at", "data_end", "n_train", "n_validation", "n_test",
        "blend_weights": {"ml_1x2", "ml_over25", "ml_btts"},     # ML vs Dixon-Coles (validation)
        "market_weights": {"1x2", "over25", "btts"},             # model vs market (validation)
        "holdout_vs_market_1x2", "holdout_vs_market_over25",     # test window
        "backtest_1x2_model_only", "backtest_1x2_market_aware", ...
    },
}
```

`Football/data/processed/model_metrics.json` mirrors `metrics` (without feature importances).
Tennis keeps `atp/wta_model.pkl` + `atp/wta_pipeline.pkl` with metrics in
`Tennis/data/processed/model_metrics.json` (`market_weight`, `holdout_vs_market`, backtests).

## Value-pick rule

A selection is recommended only if, after shrinking the model toward the market:
`3% <= EV <= 15%`, odds <= 3.20, probability >= 30% (football), the prediction is not low
confidence (cross-league cup ties), and the competition and market were validated against
historical prices (domestic 1X2 and O/U goals). See `FootballPredictor.predict_match` and
`tennis_core.betting.value.analyze_betting_value`.

## Daily pipeline

`scripts/run_daily_pipeline.py`: refresh data → retrain when due (weekly / forced / stale / old
schema) through the promotion gate (`sports_common.evaluation.should_promote`), otherwise rebuild
the feature state in memory → fetch fixtures, predict, log → reconcile → export payload.
