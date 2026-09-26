# BRIEFING — 2026-09-26T15:26:00Z

## Mission
Train production-ready International Football ML model bundle (1X2, Over/Under 2.5, BTTS) using historical results (1872-2026) with calibrated LightGBM models, achieving >40% out-of-sample accuracy.

## 🔒 My Identity
- Archetype: implementer
- Roles: implementer, qa, specialist
- Working directory: /home/antoine/Code/AG_sports_data/.agents/teamwork/worker_m2
- Original parent: 46f6f8cd-21b3-4356-b686-bf78b91e125f
- Milestone: Milestone 2: International Football ML Model Training

## 🔒 Key Constraints
- Strict Grounding: ZERO tolerance for hallucination or simulated/invented data. Only real historical data from Football/data/raw/International/results.csv.
- Exclusive write ownership:
  * Football/football_core/models/train_international.py
  * Football/football_core/models/international_features.py
  * Football/models_saved/International_bundle.joblib
- Do NOT edit other files.
- Elo initialization: 1872-2017 historical matches (~41,300 matches) as prior; 2018-2026 evaluation/training.
- Models: LightGBM with CalibratedClassifierCV (sigmoid, TimeSeriesSplit).
- Metrics: Out-of-sample 1X2 accuracy > 40%.
- Bundle output format: dict with league_key="International", pipeline, models (model_1x2, model_over25, model_btts, base_1x2), metrics.

## Current Parent
- Conversation ID: 46f6f8cd-21b3-4356-b686-bf78b91e125f
- Updated: 2026-09-26T15:26:00Z

## Task Summary
- **What to build**: International feature engineering pipeline + model training script + saved model bundle (`International_bundle.joblib`).
- **Success criteria**: Genuine feature calculation on 49,547 matches, out-of-sample test accuracy > 40%, bundle saved and loadable, build_inference_features working.
- **Interface contracts**: PROJECT.md, explorer_survey_ml/handoff.md.

## Change Tracker
- **Files modified**:
  * `Football/football_core/models/international_features.py`: Feature pipeline with Elo (1872-2017 historical replay), rolling form, H2H, and inference feature builder.
  * `Football/football_core/models/train_international.py`: Calibrated LightGBM models (1X2, O/U 2.5, BTTS), comparative evaluation vs combined model, bundle generation.
  * `Football/models_saved/International_bundle.joblib`: Serialized bundle containing fitted pipeline, calibrated models, and test metrics (18.3 MB).
- **Build status**: Pass.
- **Pending issues**: None.

## Quality Status
- **Build/test result**: Pass (61.03% 1X2 accuracy, > 40% threshold exceeded by +21.03 percentage points).
- **Lint status**: Clean (py_compile passed).
- **Tests added/modified**: Verified loadability, inference prediction (France vs Germany, Brazil vs Argentina), and 0 forbidden random generators.

## Loaded Skills
- None.

## Key Decisions Made
- Deployed Separate International-Only Model for production bundle: maintains domain specificity, eliminates domestic parity shift, and accurately models neutral venues and extreme Elo gradients.
- Replayed 41,300 pre-2018 matches through Elo, Form, and H2H engines to ensure authentic priors for 317 national teams entering 2018.

## Artifact Index
- DISPATCH.md — Assignment instructions
- BRIEFING.md — Situational awareness
- progress.md — Liveness & progress tracker
- handoff.md — Final 5-component handoff report
