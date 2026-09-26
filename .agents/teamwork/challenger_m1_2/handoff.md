# Handoff Report: Milestone 1 — Challenger 2 (Adversarial Stress Test)

**Agent**: Challenger 2 (Empirical Challenger: Critic & Specialist)  
**Date**: 2026-09-26  
**Status**: Completed  
**Verdict**: **REQUEST_CHANGES**  
**Handoff File**: `/home/antoine/Code/AG_sports_data/.agents/teamwork/challenger_m1_2/handoff.md`  
**Test Suite Created**: `/home/antoine/Code/AG_sports_data/tests/test_milestone1_adversarial.py`  

---

## 1. Observation

### 1.1 Config Integrity (`Football/football_core/config.py`)
- Verified that `LEAGUES` contains exactly 22 competitions:
  - 9 European domestic leagues (`EPL`, `LaLiga`, `SerieA`, `Bundesliga`, `Ligue1`, `Belgium`, `Eredivisie`, `PrimeiraLiga`, `ScottishPrem`).
  - 3 European club cups (`UCL`, `UEL`, `UECL`).
  - 10 International competitions (`NationsLeague`, `WorldCup`, `WCQ_UEFA`, `WCQ_CONMEBOL`, `WCQ_CAF`, `Euro`, `CopaAmerica`, `AFCON`, `Friendlies`, `GoldCup`).
- All 22 competitions define all 7 required schema keys: `name`, `country`, `code`, `espn_code`, `flag`, `is_cup`, `is_international`.
- Values are strictly typed:
  - `is_cup` is strictly `bool` (False for the 9 domestic leagues, True for the 3 European cups and 10 international tournaments).
  - `is_international` is strictly `bool` (False for domestic leagues and European cups, True for all 10 international tournaments).
  - `odds_key` is `None` for all 10 international tournaments, and non-empty strings for domestic leagues and European cups.
  - `espn_code` values are 100% unique and 100% synchronized with `ESPN_LEAGUE_CODES` in `Football/football_core/data/espn_client.py`.
  - `code` values are 100% unique.

### 1.2 Bypassing Domestic Downloaders (`fetcher.py` and `auto_update.py`)
- In `Football/football_core/data/fetcher.py`:
  - `fetch_all_data(force=False)` (lines 61–73):
    ```python
    for league_key, info in LEAGUES.items():
        if info.get("is_cup"):
            continue
    ```
    Mocking `download_league_season` proved that `fetch_all_data` invoked downloads ONLY for the 9 domestic leagues. All 13 competitions with `is_cup=True` were skipped.
  - `update_active_seasons(active_seasons=None)` (lines 76–89):
    ```python
    for league_key, info in LEAGUES.items():
        if info.get("is_cup"):
            continue
    ```
    Mocking `download_league_season` proved that `update_active_seasons` invoked downloads ONLY for the 9 domestic leagues.
- In `Football/football_core/data/auto_update.py`:
  - `check_and_auto_update(force=False)` (lines 38–70):
    ```python
    for league_key, league_info in LEAGUES.items():
        if league_info.get("is_cup"):
            continue
    ```
    Mocking `download_league_season`, `load_raw_league_data`, `clean_match_data`, and `save_processed_data` proved that only the 9 domestic leagues are processed. Zero cup or international competitions trigger domestic CSV downloading.
- Direct invocation of `download_league_season("WorldCup", "9999", force=False)` returned `None` cleanly with a logged warning, without unhandled exceptions.

### 1.3 Team Name Normalization & `teams_match` (`Football/football_core/utils/helpers.py`)
- Tested 55+ national team variations across all FIFA confederations (UEFA, CONMEBOL, CAF, CONCACAF, AFC).
- When aliases are provided in standard Title Case (e.g. `USA`, `Côte d'Ivoire`, `Türkiye`, `Czechia`, `Bosnia-Herzegovina`, `Korea Republic`, `IR Iran`, `Congo DR`, `Cabo Verde`, `Ireland`, `FYR Macedonia`, `Trinidad & Tobago`, `St. Vincent / Grenadines`, `St. Kitts and Nevis`), `teams_match` evaluates to `True` (100% match rate across positive test cases).
- Symmetry (`teams_match(a, b) == teams_match(b, a)`) and reflexivity (`teams_match(a, a) == True`) held for all 55+ variations.

### 1.4 Empirical Vulnerabilities Discovered
Adversarial stress-testing surfaced three critical defects in `Football/football_core/utils/helpers.py`:

1. **Vulnerability 1: Missing standalone alias `"Bosnia"` in `NATIONAL_TEAM_MAP`**
   - Lines 298–333 in `helpers.py`:
     ```python
     "Bosnia-Herzegovina": "Bosnia and Herzegovina",
     "Bosnia and Herzegovina": "Bosnia and Herzegovina",
     ```
     Standalone `"Bosnia"` is omitted from `NATIONAL_TEAM_MAP`.
   - Result: `normalize_team_name("Bosnia")` returns `"Bosnia"`.
   - In `Football/data/raw/International/results.csv`, the canonical dataset name is `"Bosnia and Herzegovina"`. Direct lookups for `"Bosnia"` in `results.csv` return 0 matches.

2. **Vulnerability 2: Case-sensitivity in `normalize_team_name` breaks lowercase alias matching**
   - Lines 403–408 in `helpers.py`:
     ```python
     def normalize_team_name(name: str) -> str:
         if not name or not isinstance(name, str):
             return ""
         clean = name.strip()
         return TEAM_NAME_MAP.get(clean, clean)
     ```
   - No case-folding is applied prior to dictionary lookup.
   - When lowercase variations are provided:
     - `normalize_team_name("usa")` returns `"usa"`, and `teams_match("usa", "United States")` returns `False`!
     - `normalize_team_name("czechia")` returns `"czechia"`, and `teams_match("czechia", "Czech Republic")` returns `False`!
     - `normalize_team_name("cote d'ivoire")` returns `"cote d'ivoire"`, and `teams_match("cote d'ivoire", "Ivory Coast")` returns `False`!

3. **Vulnerability 3: Severe False-Positive Collisions on Distinct Sovereign Nations in `teams_match`**
   - Lines 389–390 and 396–397 in `helpers.py`:
     ```python
     if len(c1) >= 4 and len(c2) >= 4 and (c1 in c2 or c2 in c1):
         return True
     ...
     overlap = w1.intersection(w2)
     if any(w not in ["real", "club", "atletico", "sporting", "city", "united", "town", "deportivo"] for w in overlap):
         return True
     ```
   - Because stop words are limited to domestic club qualifiers (`"real"`, `"club"`, etc.), unanchored substring matching and non-stopped single-token overlap cause distinct sovereign nations to evaluate to `True`:
     * `teams_match("Niger", "Nigeria")` -> `True` (`"niger"` is substring of `"nigeria"`)
     * `teams_match("South Korea", "North Korea")` -> `True` (shared token `"korea"`)
     * `teams_match("Republic of Ireland", "Northern Ireland")` -> `True` (shared token `"ireland"`)
     * `teams_match("Congo", "DR Congo")` -> `True` (shared token `"congo"`)
     * `teams_match("Sudan", "South Sudan")` -> `True` (shared token `"sudan"`)
     * `teams_match("Guinea", "Guinea-Bissau")` -> `True` (shared token `"guinea"`)
     * `teams_match("Guinea", "Equatorial Guinea")` -> `True` (shared token `"guinea"`)
     * `teams_match("Manchester City", "Manchester United")` -> `True` (shared token `"manchester"`)
   - Because `teams_match` is directly utilized in `Football/football_core/betting/tracker.py` (lines 267–269), `Football/football_core/data/espn_client.py` (lines 465–472, 586–587), and `Football/football_core/data/api_football.py` (line 152), this collision flaw risks reconciling completed match outcomes to the wrong sovereign nation.

---

## 2. Logic Chain

1. **Premise 1 (Config Integrity)**: All 22 competitions must be properly defined with valid schemas, correct types, and synchronized ESPN codes to enable downstream model and fixture routing.
   - *Observation*: Verification confirmed 22 competitions with 100% required keys, strict booleans, and 100% unique, synchronized ESPN codes.
   - *Inference*: Area 1 is sound and verified.

2. **Premise 2 (Downloader Isolation)**: International competitions and European cups lack football-data.co.uk division CSV files and must never be fetched by domestic data routines.
   - *Observation*: `fetch_all_data`, `update_active_seasons`, and `check_and_auto_update` all guard with `if info.get("is_cup"): continue`. Mocks confirmed that zero cup or international competitions are queried during automated routines.
   - *Inference*: Area 2 is sound and verified.

3. **Premise 3 (Normalization Robustness & Reconciler Integrity)**: Team normalization and fuzzy matching must be robust to casing, cover all common aliases, and avoid false matches across distinct nations.
   - *Observation*:
     1. `"Bosnia"` is not in `NATIONAL_TEAM_MAP`.
     2. `normalize_team_name` does exact-case lookup; lowercase aliases (`"usa"`, `"czechia"`, `"cote d'ivoire"`) fail to normalize and fail `teams_match`.
     3. `teams_match` matches `Niger` to `Nigeria`, `South Korea` to `North Korea`, `Republic of Ireland` to `Northern Ireland`, `Congo` to `DR Congo`, and `Manchester City` to `Manchester United`.
   - *Inference*: These defects violate identity isolation and data reconciliation guarantees, requiring remediation before proceeding to downstream feature pipelines and prediction reconciliation.

---

## 3. Caveats

- **Sandbox Egress Restrictions**: Direct network calls to `site.api.espn.com` are blocked by sandbox egress security rules (HTTP 403). Downloader logic and fixture routines were tested against local configurations, unit test mocks, and existing cached payloads.
- **Off-Cycle Tournament Fixture Windows**: In non-tournament periods (such as late September), international schedules on ESPN legitimately show zero fixtures. This is compliant with strict anti-hallucination rules.

---

## 4. Conclusion

**Verdict**: **REQUEST_CHANGES**

Worker 1 must implement the following targeted corrections:

1. **Update `Football/football_core/utils/helpers.py:NATIONAL_TEAM_MAP`**:
   Add standalone `"Bosnia": "Bosnia and Herzegovina"` to `NATIONAL_TEAM_MAP`.
2. **Make `normalize_team_name` case-insensitive**:
   Build a case-folded lookup table (e.g. `_LOWER_TEAM_NAME_MAP = {k.lower(): v for k, v in TEAM_NAME_MAP.items()}`) and fallback to case-insensitive lookup in `normalize_team_name` when exact lookup fails:
   ```python
   def normalize_team_name(name: str) -> str:
       if not name or not isinstance(name, str):
           return ""
       clean = name.strip()
       if clean in TEAM_NAME_MAP:
           return TEAM_NAME_MAP[clean]
       return _LOWER_TEAM_NAME_MAP.get(clean.lower(), clean)
   ```
3. **Prevent False-Positive Sovereign Nation Collisions in `teams_match`**:
   - Add `"man"`, `"manchester"` to excluded generic words.
   - Restrict substring containment (`len >= 4`) so it does not match across word boundaries when distinct directional or political qualifiers exist (`"North"` vs `"South"`, `"Republic"` vs `"Democratic"`, `"Northern"` vs `"Republic"`), or require word boundary matches for country tokens (`"Niger"` vs `"Nigeria"`).
   - Ensure `teams_match("Niger", "Nigeria")`, `teams_match("South Korea", "North Korea")`, `teams_match("Republic of Ireland", "Northern Ireland")`, `teams_match("Congo", "DR Congo")`, `teams_match("Sudan", "South Sudan")`, `teams_match("Guinea", "Guinea-Bissau")`, and `teams_match("Manchester City", "Manchester United")` all evaluate to `False`.

---

## 5. Verification Method

To independently execute and verify the entire test harness:

```bash
# Run Challenger 2 adversarial suite
.venv/bin/python -m unittest tests/test_milestone1_adversarial.py -v

# Run all test suites in the workspace
.venv/bin/python -m unittest discover -s tests -p "test_*.py" -v

# Verify TypeScript build
cd web && npx tsc --noEmit

# Verify zero hallucinated random generators
.venv/bin/python -c "
import subprocess
res = subprocess.run(['grep', '-rn', '--include=*.py', '-E', 'random\.(seed|choice|gauss|randint|sample)', 'Football', 'scripts'], capture_output=True, text=True)
lines = [l for l in res.stdout.strip().splitlines() if l and not 'random_state' in l]
assert len(lines) == 0, f'Found violations: {lines}'
print('Anti-hallucination verified: 0 forbidden random generators!')
"

# Verify tracker integrity (203 football, 200 tennis)
.venv/bin/python -c "
import json
with open('Football/data/cache/predictions_tracker.json') as f:
    assert len(json.load(f)) == 203
with open('Tennis/data/tracker/predictions_archive.json') as f:
    assert len(json.load(f)) == 200
print('Tracker integrity verified: 203 football, 200 tennis.')
"
```
