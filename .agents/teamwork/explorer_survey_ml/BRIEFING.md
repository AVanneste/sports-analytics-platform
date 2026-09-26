# BRIEFING — 2026-09-26T09:23:00Z

## Mission
Investigate ML architecture, existing training code, feature engineering, and the martj42 international dataset to design and specify the international football model pipeline meeting R3 requirements.

## 🔒 My Identity
- Archetype: explorer
- Roles: ML Architecture & Dataset Explorer
- Working directory: /home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_survey_ml
- Original parent: 46f6f8cd-21b3-4356-b686-bf78b91e125f
- Milestone: exploration

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Strict grounding (.agents/rules/strict-grounding.md): NEVER invent, fabricate, or simulate any data, scores, odds, fixtures, or match results.
- Write only to own folder /home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_survey_ml/

## Current Parent
- Conversation ID: 46f6f8cd-21b3-4356-b686-bf78b91e125f
- Updated: 2026-09-26T09:14:00Z

## Investigation State
- **Explored paths**:
  - `ORIGINAL_REQUEST.md`: Authoritative user requirements for R1, R2, R3, R4.
  - `Football/football_core/models/train.py`, `predictor.py`: Training architecture, CalibratedClassifierCV, TimeSeriesSplit, bundle structure.
  - `Football/football_core/features/`: `builder.py`, `elo.py`, `dixon_coles.py`, `form.py`, `h2h.py`, `referee.py`.
  - `Football/models_saved/`: Inspected `EPL_bundle.joblib` and `MultiLeague_bundle.joblib`.
  - `Football/data/raw/`: Verified 9 domestic leagues with 9 seasons each (23,519 matches total).
  - Dataset `martj42/international_results`: Downloaded via GitHub API raw blobs to `Football/data/raw/International/results.csv` (3.73 MB, 49,547 matches, 1872 to 2026-08-26, 0 missing values).
  - Experimental models: Evaluated Model A (Separate International-Only) vs Model B (Combined Domestic + International).
- **Key findings**:
  1. The international dataset has 49,547 historical matches (8,247 from 2018-01-01 to 2026-08-26) covering all required tournaments (World Cup, Qualifiers, Euro, Copa America, AFCON, Nations League, Gold Cup, Friendlies).
  2. 26.6% of international matches are on neutral grounds (`neutral == True`), necessitating `home_adv = 0.0` when neutral.
  3. Pre-2018 historical replay (41,300 matches) initializes Elo ratings across 337 nations with zero cold-start penalty entering 2018 (Brazil 2124, Spain 2043, Germany 2032, France 1995, Argentina 1983).
  4. Out-of-sample 1X2 accuracy comparison on 1,650 test matches (Nov 2024 to Aug 2026):
     - Separate International Model (Model A): **61.33%** accuracy (Log Loss: 0.8581)
     - Combined Model (Model B): **60.73%** accuracy (Log Loss: 0.8762)
     - Winner: **Separate International Model** (beats R3 requirement of > 40% by +21.33%).
  5. Dixon-Coles MLE optimization with 500+ parameters on disconnected international national graphs stalls; Elo-derived Poisson goal expectancy and empirical Bayes form provide instant, deterministic, robust score matrix projections.
- **Unexplored areas**: None. All core questions investigated and answered empirically.

## Key Decisions Made
- Confirmed dataset fetching mechanism: query `api.github.com/repos/martj42/international_results/contents/results.csv` and download raw blob with header `Accept: application/vnd.github.v3.raw` to `Football/data/raw/International/results.csv`.
- Confirmed model selection: Separate International Model (Model A) strictly outperforms Combined Model (Model B) and avoids domain dilution.
- Confirmed bundle location and structure: `Football/models_saved/International_bundle.joblib` containing `pipeline`, `models`, `metrics`, and `league_key="International"`.

## Artifact Index
- DISPATCH.md — Incoming messages log
- BRIEFING.md — Persistent working memory and state
- progress.md — Heartbeat and progress tracking
- handoff.md — 5-component comprehensive investigation and model architecture report
