## 2026-09-26T15:15:25Z
You are Worker 1 for Milestone 2: International Football ML Model Training.
Working directory: /home/antoine/Code/AG_sports_data/.agents/teamwork/worker_m2/
Authoritative request file: /home/antoine/Code/AG_sports_data/.agents/teamwork/ORIGINAL_REQUEST.md (read this first).
Project blueprint file: /home/antoine/Code/AG_sports_data/PROJECT.md
Detailed technical blueprint & ML survey: /home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_survey_ml/handoff.md
Strict rules: Read and follow .agents/rules/strict-grounding.md. NEVER invent, fabricate, or simulate any data, scores, odds, fixtures, or match results. Only use real historical data from Football/data/raw/International/results.csv.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Exclusive file write ownership:
- Football/football_core/models/train_international.py
- Football/football_core/models/international_features.py (optional if split, or inline in train_international.py)
- Football/models_saved/International_bundle.joblib
Do NOT edit other files.

Your implementation tasks:
1. Implement the feature pipeline for international football:
   - Use Football/data/raw/International/results.csv (49,547 real historical matches).
   - Initialize Elo ratings chronologically across all 1872–2017 matches (41,300 matches) so national teams enter 2018 with authentic historical priors.
   - For matches 2018–2026, compute:
     * home_elo, away_elo, elo_diff (with home_adv = 0 if neutral else 65.0)
     * elo_prob_home, elo_prob_away
     * is_neutral (0 or 1)
     * tournament_importance (weighting by competition tier: World Cup 1.0, Continental 0.85, Nations League 0.70, Qualifiers 0.65, Friendlies 0.40)
     * Rolling form (last 5 matches): home_ppg_l5, away_ppg_l5, diff_ppg_l5, home_gf_l5, away_gf_l5, home_ga_l5, away_ga_l5, home_gd_l5, away_gd_l5, diff_gd_l5
     * Head-to-head (H2H): h2h_matches_count, h2h_home_win_rate, h2h_draw_rate, h2h_away_win_rate, h2h_avg_total_goals
   - Provide an inference feature builder method: `build_inference_features(home_team, away_team, date=None, is_neutral=False, tournament=None) -> pd.DataFrame` so downstream predictor can build features for upcoming matches.

2. Implement `train_international_model(save_path: Optional[str] = None, evaluate_combined: bool = True) -> Dict[str, Any]` in Football/football_core/models/train_international.py:
   - Chronological 80/20 train/test split on 2018–2026 matches.
   - LightGBM 1X2 base classifier with CalibratedClassifierCV (sigmoid, TimeSeriesSplit).
   - LightGBM Over/Under 2.5 and BTTS models with CalibratedClassifierCV.
   - Separately evaluate combined vs separate model, document the comparison in code/metrics, and save the superior model (separate international model).
   - Ensure out-of-sample 1X2 accuracy > 40%.
   - Save trained bundle to Football/models_saved/International_bundle.joblib with structure:
     ```python
     bundle = {
         "league_key": "International",
         "pipeline": pipeline,
         "models": {
             "model_1x2": cal_1x2,
             "model_over25": cal_ou,
             "model_btts": cal_btts,
             "base_1x2": model_1x2_base,
         },
         "metrics": metrics,
     }
     ```

3. Verification:
   - Run: `PYTHONPATH=".:Football" python -c "from football_core.models.train_international import train_international_model; train_international_model()"`
   - Confirm Football/models_saved/International_bundle.joblib exists, is loadable with joblib.load, and reports out-of-sample accuracy > 40%.
   - Test inference prediction with a sample pair (e.g. France vs Germany).
   - Confirm 0 forbidden random generators outside random_state=42.

4. Write handoff report to /home/antoine/Code/AG_sports_data/.agents/teamwork/worker_m2/handoff.md and message parent.
