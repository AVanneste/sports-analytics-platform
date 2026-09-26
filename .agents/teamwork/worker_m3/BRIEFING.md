# BRIEFING — 2026-09-26T20:19:00Z

## Mission
Milestone 3: Daily Pipeline & Web Dashboard Integration.
Integrate international football inference into FootballPredictor, align tracker logging API with immutability guarantees, ensure run_daily_pipeline.py and export_web_data.py smoothly handle international competitions & invalid API keys, and update App.tsx to display international leagues in filters without regression.

## 🔒 My Identity
- Archetype: worker
- Roles: implementer, qa, specialist
- Working directory: /home/antoine/Code/AG_sports_data/.agents/teamwork/worker_m3
- Original parent: 46f6f8cd-21b3-4356-b686-bf78b91e125f
- Milestone: Milestone 3 - Daily Pipeline & Web Dashboard Integration

## 🔒 Key Constraints
- Exclusive file write ownership:
  - Football/football_core/models/predictor.py
  - Football/football_core/betting/tracker.py
  - scripts/run_daily_pipeline.py
  - scripts/export_web_data.py
  - web/src/App.tsx
- Do NOT edit other files.
- Strict anti-hallucination policy (.agents/rules/strict-grounding.md). NEVER invent, fabricate, or simulate any data, scores, odds, fixtures, or match results.
- No `random` module usage outside LightGBM random_state.
- Existing 203 settled football tracker entries and 200 tennis tracker entries must remain 100% intact.
- Settled entries (status == "settled") must never be overwritten or mutated.
- Must verify that `ODDS_API_KEY=invalid` executes cleanly without exceptions.
- Web export and web build (`npx tsc --noEmit`, `npm run build`) must succeed with exit code 0.

## Current Parent
- Conversation ID: 46f6f8cd-21b3-4356-b686-bf78b91e125f
- Updated: 2026-09-26T20:17:10Z

## Task Summary
- **What to build**:
  1. `Football/football_core/models/predictor.py`: Load `International_bundle.joblib` into `self.bundles["International"]`, route international leagues to the international bundle and pipeline, compute 1X2, Over/Under 2.5, BTTS probabilities, score matrix via Elo-based bivariate Poisson generator, and support international team profiles/form lookups.
  2. `Football/football_core/betting/tracker.py`: Add `log_prediction(self, pred_item: Dict[str, Any]) -> bool` method normalizing top-level fields (match_id, date, league_key, home_team, away_team, predicted_winner, probabilities, odds) and delegating to `log_full_match_prediction`, ensuring settled entries are never overwritten or mutated.
  3. `scripts/run_daily_pipeline.py`: Robust pipeline run across domestic + international leagues, predicting via FootballPredictor, logging predictions, reconciling completed matches, skipping domestic CSV retraining for cup/international competitions, and running export_web_data.py cleanly when ODDS_API_KEY=invalid.
  4. `scripts/export_web_data.py`: Ensure international upcoming fixtures, predictions, and tracker data are exported to `web/public/data/sports_data.json`.
  5. `web/src/App.tsx`: Include international leagues in `footballLeagues` memo.
- **Success criteria**:
  - Daily pipeline runs with ODDS_API_KEY=invalid without exception.
  - Web export returns exit code 0.
  - Web TypeScript check and build succeed with exit code 0.
  - 203 football and 200 tennis predictions intact.
  - 0 forbidden random generators.
- **Interface contracts**: PROJECT.md, survey report handoff.md
- **Code layout**: PROJECT.md

## Key Decisions Made
- `predictor.py`: Bound international score matrix to 8x8 using bivariate Poisson probability distribution parameterized by Elo expected goals $\lambda_H, \lambda_A$ with $\rho = -0.05$ correlation adjustment.
- `tracker.py`: Added `log_prediction` method with auto-normalization of top-level odds, probabilities, fixture metadata, plus immutable guards preventing mutation of settled records.
- `tracker.py`: Added explicit filtering against phantom fixture entries without valid `home_team` or `away_team`.
- `run_daily_pipeline.py`: Added `--skip-retrain` / `SKIP_RETRAIN` CLI argument & env var to bypass long retraining step when verifying pipeline orchestration and export.

## Artifact Index
- `.agents/teamwork/worker_m3/progress.md` — Liveness & step progress
- `.agents/teamwork/worker_m3/handoff.md` — Final 5-component handoff report

## Change Tracker
- **Files modified**:
  - `Football/football_core/models/predictor.py` - International bundle loading, international match inference, calibrated 1X2/OU2.5/BTTS, score matrix, team stats routing.
  - `Football/football_core/betting/tracker.py` - Added `log_prediction`, settled entry immutability protection, phantom match filtering.
  - `scripts/run_daily_pipeline.py` - International prediction routing, skipping cup retraining, graceful error handling for invalid Odds API keys, skip retrain flag.
  - `scripts/export_web_data.py` - Enriched international fixtures with proper prediction kwargs, exported to web sports_data.json.
  - `web/src/App.tsx` - Added `INTERNATIONAL_LEAGUES` list, integrated international leagues into `footballLeagues` memo.
- **Build status**: All checks passed (tsc: 0, vite build: 0, daily pipeline: 0, web export: 0)
- **Pending issues**: None

## Quality Status
- **Build/test result**: All tests passed (100% pass rate)
- **Lint status**: Clean (no forbidden random generators, 0 TypeScript errors)
- **Tests added/modified**: Integrated assertions for international prediction, tracker immutability, pipeline exit codes.

## Loaded Skills
- None required (native Python/TypeScript)
