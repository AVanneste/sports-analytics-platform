# Milestone 2 Handoff Report: International Football ML Model Training

**Worker**: Worker 1 (Milestone 2 Implementer / QA / Specialist)  
**Date**: 2026-09-26  
**Status**: Completed  
**Artifacts Generated**:
- `Football/football_core/models/international_features.py`
- `Football/football_core/models/train_international.py`
- `Football/models_saved/International_bundle.joblib`

---

## 1. Observation

### 1.1 Dataset Properties
- **Dataset Path**: `Football/data/raw/International/results.csv`
- **Total Historical Matches**: 49,547 matches spanning 1872-11-30 to 2026-08-26.
- **Pre-2018 Matches (Priors Initialization)**: 41,300 matches (1872-11-30 to 2017-12-31).
- **Modern Matches (Model Training & Evaluation)**: 8,247 matches (2018-01-01 to 2026-08-26).
- **Teams Tracked**: 317 distinct national teams initialized entering 2018.

### 1.2 Model Performance & Out-of-Sample Metrics
On a strict chronological 80/20 train/test split on modern matches:
- **Train Slice**: 6,597 matches (2018-01-02 to late-2024).
- **Test Slice**: 1,650 matches (late-2024 to 2026-08-26).
- **1X2 Classifier**:
  - Out-of-sample Accuracy: **61.03%** (Exceeds >40.0% acceptance threshold by +21.03 percentage points).
  - Out-of-sample Log Loss: **0.8572**.
  - Out-of-sample Brier Score: **0.5017**.
- **Over/Under 2.5 Goals Classifier**:
  - Out-of-sample Accuracy: **56.30%**.
- **Both Teams To Score (BTTS) Classifier**:
  - Out-of-sample Accuracy: **55.88%**.

### 1.3 Comparative Evaluation: Separate vs. Combined Models
- **Separate International Model** (6,597 training samples):
  - 1X2 Out-of-Sample Accuracy: **61.03%**
  - Out-of-Sample Log Loss: **0.8572**
- **Combined Domestic + International Model** (30,116 training samples = 6,597 international + 23,519 domestic matches):
  - 1X2 Out-of-Sample Accuracy: **61.82%**
  - Out-of-Sample Log Loss: **0.8560**
- **Architecture Decision**: Both models perform similarly (>61%), but the **Separate International Model** is preserved in the bundle as specified by project dispatch ("Separately evaluate combined vs separate model, document the comparison in code/metrics, and save the superior model (separate international model)"). The separate model avoids domestic club schedule assumptions, handles 26.56% neutral venue matches authentically without domestic home-field bias, and strictly mirrors the international talent gradient. Both evaluations are formally preserved in `metrics["model_comparison"]`.

### 1.4 Anti-Hallucination & Random Generator Compliance
- Running grep for prohibited random calls:
  `grep -rn --include=*.py -E 'random\.(seed|choice|gauss|randint|sample)' Football scripts`
  returned **0 hits** across the entire codebase outside of LightGBM's deterministic `random_state=42`.
- All features and ratings are computed solely from real match scorelines, dates, neutrality flags, and tournament designations in `results.csv`.

---

## 2. Logic Chain

1. **Premise 1 (Cold-Start Priors)**: Training on modern matches starting in 2018 with base 1500.0 Elo ratings would misrepresent established football hierarchies (e.g., treating Brazil and San Marino as equal in Jan 2018). Replaying all 41,300 matches from 1872 to 2017 establishes authentic priors (Brazil ~2125, Germany ~2043, France ~1999) before the modern training window opens.
2. **Premise 2 (Feature Alignment)**: To predict international fixtures where corners, cards, and referee assignments are absent from historical records, a 22-dimensional feature schema was engineered based on:
   - Dynamic Elo ratings (`home_elo`, `away_elo`, `elo_diff`, `elo_prob_home`, `elo_prob_away`) with neutral venue awareness (`home_adv = 0.0` if neutral, 65.0 otherwise).
   - Competition tier weighting (`tournament_importance` ranging from 0.40 for friendlies to 1.00 for World Cup finals).
   - Rolling 5-match form (`home_ppg_l5`, `away_ppg_l5`, `diff_ppg_l5`, `home_gf_l5`, `away_gf_l5`, `home_ga_l5`, `away_ga_l5`, `home_gd_l5`, `away_gd_l5`, `diff_gd_l5`).
   - Head-to-head metrics (`h2h_matches_count`, `h2h_home_win_rate`, `h2h_draw_rate`, `h2h_away_win_rate`, `h2h_avg_total_goals`).
3. **Premise 3 (Probability Calibration)**: Raw LightGBM tree leaves can produce overconfident probabilities. Applying `CalibratedClassifierCV(method='sigmoid', cv=TimeSeriesSplit(n_splits=5))` ensures that predicted class probabilities correspond to true empirical frequencies across multi-class (1X2) and binary (O/U 2.5, BTTS) markets.
4. **Premise 4 (Production Bundle Structure)**: Downstream predictors require a standard interface. `International_bundle.joblib` bundles `league_key="International"`, the fitted `pipeline`, the trained models dictionary (`model_1x2`, `model_over25`, `model_btts`, `base_1x2`), and the evaluation `metrics` dictionary.

---

## 3. Caveats

1. **In-Match Stats for Corners and Cards**: Historical international match records in `results.csv` do not include corners or cards. Consequently, corners and cards models are omitted from `International_bundle.joblib` (unlike domestic league bundles which train on football-data.co.uk stats).
2. **Team Name Resolution**: National team names in incoming ESPN fixtures can vary (e.g. "USA" vs "United States", "Korea Republic" vs "South Korea"). The pipeline includes `normalize_intl_team_name` and case-insensitive/accent-stripped fuzzy resolution to ensure consistent lookup.
3. **Python Environment**: In sandboxed environments where `/usr/bin/python` is not configured, commands should be executed either via `.venv/bin/python` or after running `source .venv/bin/activate`.

---

## 4. Conclusion

- Milestone 2 is fully implemented, verified, and operational.
- The feature pipeline in `Football/football_core/models/international_features.py` accurately processes all 49,547 historical matches and provides `build_inference_features` for downstream predictions.
- `Football/football_core/models/train_international.py` runs end-to-end without errors and saves the model bundle to `Football/models_saved/International_bundle.joblib`.
- Out-of-sample 1X2 accuracy is **61.03%**, exceeding the 40.0% acceptance criterion by +21.03 percentage points.

---

## 5. Verification Method

### 5.1 End-to-End Retraining Verification
Run the training script via activated virtual environment:
```bash
source .venv/bin/activate && PYTHONPATH=".:Football" python -c "from football_core.models.train_international import train_international_model; train_international_model()"
```
*Expected Result*: Loads 49,547 matches, initializes 317 teams across 41,300 matches, trains calibrated LightGBM models, reports 1X2 accuracy > 40%, and saves `International_bundle.joblib`.

### 5.2 Bundle Load & Sample Inference Verification
```bash
.venv/bin/python -c "
import joblib
bundle = joblib.load('Football/models_saved/International_bundle.joblib')
print('Keys:', bundle.keys())
assert bundle['league_key'] == 'International'
assert bundle['metrics']['acc_1x2'] > 0.40
pipeline = bundle['pipeline']
models = bundle['models']

# Test France vs Germany
X = pipeline.build_inference_features('France', 'Germany', is_neutral=False, tournament='UEFA Nations League')
probs = models['model_1x2'].predict_proba(X)[0]
print('France vs Germany 1X2 Probs (H/D/A):', [round(p, 3) for p in probs])
assert len(probs) == 3
assert abs(sum(probs) - 1.0) < 1e-4
print('Bundle & Inference verification PASSED!')
"
```

### 5.3 Anti-Hallucination Directives Check
```bash
.venv/bin/python -c "
import subprocess
res = subprocess.run(['grep', '-rn', '--include=*.py', '-E', 'random\.(seed|choice|gauss|randint|sample)', 'Football', 'scripts'], capture_output=True, text=True)
assert not res.stdout.strip(), f'Violations found: {res.stdout}'
print('Zero forbidden random calls verified!')
"
```
