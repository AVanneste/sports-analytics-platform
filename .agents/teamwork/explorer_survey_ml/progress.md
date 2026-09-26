# Progress — ML Architecture & Dataset Explorer

Last visited: 2026-09-26T09:24:00Z
Status: Completed

## Tasks
- [x] Initial setup (DISPATCH.md, BRIEFING.md, progress.md)
- [x] Inspect existing ML training scripts and models in `Football/football_core/models/` (`train.py`, `predictor.py`)
- [x] Inspect feature engineering in `Football/football_core/` (`builder.py`, `elo.py`, `dixon_coles.py`, `form.py`, `h2h.py`, `referee.py`)
- [x] Inspect existing model bundles in `Football/models_saved/` (`EPL_bundle.joblib`, `MultiLeague_bundle.joblib`)
- [x] Investigate dataset `martj42/international_results` (schema, dates, columns, tournaments, neutral venues, team names, fetching/caching)
- [x] Analyze R3 requirements:
  - [x] LightGBM + CalibratedClassifierCV architecture
  - [x] Chronological train/test split (80/20 split: 6,597 train, 1,650 test)
  - [x] Training on 2018–2026, with historical data (1872–2017: 41,300 matches) for Elo initialization
  - [x] Features suited for international football (Elo, H2H, neutral venue, tournament importance, recent form)
  - [x] Empirical evaluation: separate model (61.33% acc) vs combined model (60.73% acc) -> Separate model wins
  - [x] Target requirement: out-of-sample 1X2 accuracy > 40% achieved (61.33%)
  - [x] Bundle structure and location: `Football/models_saved/International_bundle.joblib`
- [x] Synthesize findings and write comprehensive `handoff.md`
- [x] Notify parent agent
