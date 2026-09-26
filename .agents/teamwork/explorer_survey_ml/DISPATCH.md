## 2026-09-26T09:13:18Z

You are the ML Architecture & Dataset Explorer.
Working directory: /home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_survey_ml/
Authoritative request file: /home/antoine/Code/AG_sports_data/.agents/teamwork/ORIGINAL_REQUEST.md (read this first).
Strict rules: Read and follow .agents/rules/strict-grounding.md. NEVER invent, fabricate, or simulate any data, scores, odds, fixtures, or match results.

Your mission:
1. Read /home/antoine/Code/AG_sports_data/.agents/teamwork/ORIGINAL_REQUEST.md.
2. Inspect existing ML training scripts and models in Football/football_core/models/, feature engineering in Football/football_core/ (Elo, Dixon-Coles, form trackers, referee analytics, etc.), and existing model bundles in Football/models_saved/.
3. Investigate the dataset:
   - https://raw.githubusercontent.com/martj42/international_results/master/results.csv
   - Check its schema, date ranges, tournament types, neutral venue indicators, columns, team names.
   - Verify how the dataset can be fetched and cached under Football/data/ (or similar standard location).
4. Analyze requirements for R3:
   - LightGBM + CalibratedClassifierCV architecture.
   - Chronological train/test split.
   - Training on at least the last 8 years (2018–2026), with historical data used for Elo ratings initialization.
   - Features suited for international football (Elo per national team, H2H, home/away/neutral venue, tournament importance weighting, recent form).
   - Evaluation requirement: evaluate combined model (domestic + international) vs separate international-only model, keep the one with higher accuracy.
   - Target requirement: out-of-sample 1X2 accuracy > 40%.
   - Target bundle location: Football/models_saved/International_bundle.joblib.
5. Write your comprehensive exploration and model architecture report to /home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_survey_ml/handoff.md.
6. Send a message to your parent (parent) summarizing your findings and linking to your handoff file.
