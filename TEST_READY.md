# Testing

```bash
pip install -e ".[dev]"
python -m pytest                 # offline suite, runs in CI on every pull request
python -m pytest -m e2e          # legacy end-to-end checks: live APIs, real data, slow
cd web && npx tsc --noEmit && npm run build
```

The offline suite never sees real credentials (`tests/conftest.py` strips them) and never writes to
the real ledgers, models or data files.

| File | Covers |
|---|---|
| `tests/test_secrets.py` | Key lookup order, placeholders, log redaction, no hardcoded keys in tracked source |
| `tests/test_ledgers.py` | Atomic writes, corrupt-file refusal, immutability, odds snapshots, Kelly PnL, tennis grading, ESPN score orientation |
| `tests/test_evaluation.py` | Vig removal, log loss/Brier, model-vs-market reports, CLV, trainer holdout helpers |
| `tests/test_training.py` | No lookahead (truncation invariance), train/serve feature equality, Dixon-Coles stability, refit on all data, promotion gate, string fixture dates |
| `tests/test_market_aware.py` | Market blending, EV credibility cap, backtests, low-confidence and unvalidated-market exclusions |
| `tests/test_pipeline.py` | Retrain schedule, in-memory state refresh equals full replay |
| `tests/test_adversarial_m1.py`, `tests/test_milestone1_adversarial.py` | Legacy checks: ESPN odds parsing, config, downloader routing |
| `tests/test_e2e_acceptance.py` | Legacy acceptance suite (opt-in `e2e`) |
