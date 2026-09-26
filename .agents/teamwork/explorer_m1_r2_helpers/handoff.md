# Handoff Report: Milestone 1 Iteration 2 (Remediation) — Explorer 1 (helpers.py)

**Agent**: Explorer 1 (`explorer_m1_r2_helpers`)  
**Target Path**: `/home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_m1_r2_helpers/handoff.md`  
**Working Directory**: `/home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_m1_r2_helpers/`  
**Date**: 2026-09-26  
**Status**: Investigation Complete  

---

## 1. Observation

### 1.1 Direct Inspection of `Football/football_core/utils/helpers.py`

1. **Unanchored Substring Matching in `teams_match` (lines 389–390)**:
   ```python
   389:    if len(c1) >= 4 and len(c2) >= 4 and (c1 in c2 or c2 in c1):
   390:        return True
   ```
   - Observed behavior:
     - `teams_match("Niger", "Nigeria")` evaluates to `True` because `"niger"` (len 5) is a contiguous substring inside `"nigeria"` (len 7).
     - `teams_match("Dominica", "Dominican Republic")` evaluates to `True` because `"dominica"` (len 8) is a contiguous substring inside `"dominican republic"` (len 18).
     - `teams_match("Sudan", "South Sudan")` evaluates to `True` because `"sudan"` is a substring in `"south sudan"`.
     - `teams_match("Congo", "DR Congo")` evaluates to `True` because `"congo"` is a substring in `"dr congo"`.
     - `teams_match("Guinea", "Guinea-Bissau")` evaluates to `True` because `"guinea"` is a substring in `"guinea-bissau"`.
     - `teams_match("Guinea", "Equatorial Guinea")` evaluates to `True` because `"guinea"` is a substring in `"equatorial guinea"`.

2. **Unanchored Token Overlap without Directional/Qualifier Guards (lines 392–400)**:
   ```python
   392:    w1 = set(c1.split())
   393:    w2 = set(c2.split())
   394:    if w1 and w2:
   395:        overlap = w1.intersection(w2)
   396:        if any(w not in ["real", "club", "atletico", "sporting", "city", "united", "town", "deportivo"] for w in overlap):
   397:            return True
   398:        if len(overlap) >= 2:
   399:            return True
   400:    return False
   ```
   - Observed behavior:
     - `teams_match("South Korea", "North Korea")` evaluates to `True` because `overlap = {"korea"}`, and `"korea"` is not in the domestic stop words list.
     - `teams_match("Republic of Ireland", "Northern Ireland")` evaluates to `True` because `overlap = {"ireland"}`, and `"ireland"` is not in the stop list.
     - `teams_match("Manchester City", "Manchester United")` evaluates to `True` because `normalize_team_name` maps them to `"Man City"` and `"Man United"`. The cleaned strings have `overlap = {"man"}`. Neither `"man"` nor `"manchester"` is in the stop words list!
     - `teams_match("Congo", "DR Congo")` evaluates to `True` on shared token `"congo"`.
     - `teams_match("Sudan", "South Sudan")` evaluates to `True` on shared token `"sudan"`.
     - `teams_match("Guinea", "Equatorial Guinea")` evaluates to `True` on shared token `"guinea"`.
     - Line 398 `if len(overlap) >= 2: return True` checks raw overlap length without excluding stop words, meaning two strings sharing only stop words (e.g. `"Republic of Ireland"` and `"Republic of the Congo"` sharing `{"republic", "of"}`) risk colliding.

3. **Case Sensitivity in `normalize_team_name` (lines 403–408)**:
   ```python
   403: def normalize_team_name(name: str) -> str:
   404:     """Normalize team name using mapping table and general cleaning."""
   405:     if not name or not isinstance(name, str):
   406:         return ""
   407:     clean = name.strip()
   408:     return TEAM_NAME_MAP.get(clean, clean)
   ```
   - Observed behavior:
     - `TEAM_NAME_MAP` keys are strict Title Case (`"USA"`, `"Czechia"`, `"Côte d'Ivoire"`).
     - `normalize_team_name("usa")` returns `"usa"`, failing to resolve to `"United States"`.
     - Consequently, `teams_match("usa", "United States")` returns `False` because `norm1 = "usa"` and `norm2 = "United States"`, with 0 shared tokens.
     - `normalize_team_name("czechia")` returns `"czechia"` and `teams_match("czechia", "Czech Republic")` returns `False`.
     - `normalize_team_name("cote d'ivoire")` returns `"cote d'ivoire"` and `teams_match("cote d'ivoire", "Ivory Coast")` returns `False`.

4. **Missing Standalone Alias `"Bosnia"` in `NATIONAL_TEAM_MAP` (lines 322–323)**:
   ```python
   322:     "Bosnia-Herzegovina": "Bosnia and Herzegovina",
   323:     "Bosnia and Herzegovina": "Bosnia and Herzegovina",
   ```
   - Observed behavior:
     - Standalone `"Bosnia"` is completely missing from `NATIONAL_TEAM_MAP` and `NATIONAL_TEAM_ALIASES`.
     - In `Football/data/raw/International/results.csv`, the canonical name is `"Bosnia and Herzegovina"` across 260+ matches.
     - `normalize_team_name("Bosnia")` returns `"Bosnia"`, which does not match historical records in `results.csv`.

---

## 2. Logic Chain

1. **Premise 1 (Anti-Hallucination & Entity Discrimination)**: Distinct sovereign nations and opposing club entities must never collide during result reconciliation, Elo calculation, or prediction settlement.
   - *Observation*: `teams_match` currently returns `True` for 8 known negative pairs (`Niger` vs `Nigeria`, `South Korea` vs `North Korea`, `Republic of Ireland` vs `Northern Ireland`, `Congo` vs `DR Congo`, `Sudan` vs `South Sudan`, `Guinea` vs `Guinea-Bissau` / `Equatorial Guinea`, `Dominica` vs `Dominican Republic`, `Manchester City` vs `Manchester United`).
   - *Inference*: The collisions stem directly from two distinct flaws: (a) unanchored substring matching `(c1 in c2 or c2 in c1)`, and (b) token overlap without directional, sovereign, or club qualifier guards and with an incomplete stop words list.
   - *Conclusion*: Substring matching must be eliminated, stop words expanded, and qualifying token guards introduced.

2. **Premise 2 (Case-Insensitive Normalization)**: Feed data from disparate sources (ESPN, Odds API, flashscore scrapers, manual feeds) may provide team names in lowercase, uppercase, or title case. Normalization must be case-insensitive and diacritic-tolerant.
   - *Observation*: `normalize_team_name` does a single exact dictionary lookup on `TEAM_NAME_MAP.get(clean, clean)`. Lowercase inputs fail to resolve.
   - *Inference*: A precomputed lowercase and accent-stripped lookup mapping `_LOWER_TEAM_NAME_MAP` will allow `O(1)` case-folded lookups without degrading exact match performance.
   - *Conclusion*: `normalize_team_name` must check exact match first, then fall back to `_LOWER_TEAM_NAME_MAP`.

3. **Premise 3 (Canonical Mapping Completeness)**: Canonical naming in `results.csv` uses `"Bosnia and Herzegovina"`, whereas ESPN and casual schedules frequently display `"Bosnia"`.
   - *Observation*: `"Bosnia"` is not a key in `NATIONAL_TEAM_MAP` or `NATIONAL_TEAM_ALIASES`.
   - *Inference*: Adding `"Bosnia": "Bosnia and Herzegovina"` to `NATIONAL_TEAM_MAP` and `NATIONAL_TEAM_ALIASES` will ensure both `normalize_team_name("Bosnia")` and `normalize_team_name("bosnia")` resolve to `"Bosnia and Herzegovina"`.

---

## 3. Caveats

- **No Source Code Changes Made**: In accordance with the Explorer role and system instructions, this investigation made zero modifications to `Football/football_core/utils/helpers.py`. The proposed logic was independently tested and verified in an isolated execution sandbox.
- **Test Suite Alignment**: In `tests/test_milestone1_adversarial.py`, Challenger 2's `TestAdversarialFindings` contains assertions specifically designed to verify that the defects *existed* (e.g., asserting `len(collisions) == 7`, asserting `normalize_team_name("Bosnia") == "Bosnia"`, asserting `teams_match("usa", "United States") == False`). When Worker 1 remediates `helpers.py`, those test assertions in `tests/test_milestone1_adversarial.py` must be updated to assert the remediated behavior (i.e. asserting 0 collisions, successful normalization of "Bosnia", and `True` for lowercase aliases).

---

## 4. Conclusion & Concrete Remediation Strategy

The remediation for `Football/football_core/utils/helpers.py` consists of 4 precise, non-breaking steps.

### Step 1: Update `NATIONAL_TEAM_MAP` and `NATIONAL_TEAM_ALIASES`

In `Football/football_core/utils/helpers.py`:
1. Add standalone `"Bosnia": "Bosnia and Herzegovina"` to `NATIONAL_TEAM_MAP` (around line 322).
2. Add `"United States": "United States"` to `NATIONAL_TEAM_MAP` (around line 300) so that canonical names also exist as explicit keys.
3. Add `"Bosnia": "Bosnia and Herzegovina"` to `NATIONAL_TEAM_ALIASES` (around line 349).

### Step 2: Implement Precomputed Case-Insensitive Lookup Table

Immediately following `TEAM_NAME_MAP.update(NATIONAL_TEAM_MAP)` (line 356), construct a case-folded and accent-stripped lookup mapping:

```python
# Build case-insensitive and accent-stripped lookup index for fast O(1) matching
_LOWER_TEAM_NAME_MAP = {}
for k, v in TEAM_NAME_MAP.items():
    _LOWER_TEAM_NAME_MAP[k.lower()] = v
    _LOWER_TEAM_NAME_MAP[strip_accents(k)] = v
for v in set(TEAM_NAME_MAP.values()):
    _LOWER_TEAM_NAME_MAP[v.lower()] = v
    _LOWER_TEAM_NAME_MAP[strip_accents(v)] = v
```

### Step 3: Update `normalize_team_name`

Update `normalize_team_name` (lines 403–408) to perform case-insensitive fallback:

```python
def normalize_team_name(name: str) -> str:
    """Normalize team name using mapping table and general cleaning."""
    if not name or not isinstance(name, str):
        return ""
    clean = name.strip()
    if clean in TEAM_NAME_MAP:
        return TEAM_NAME_MAP[clean]
    low = clean.lower()
    if low in _LOWER_TEAM_NAME_MAP:
        return _LOWER_TEAM_NAME_MAP[low]
    acc = strip_accents(clean)
    if acc in _LOWER_TEAM_NAME_MAP:
        return _LOWER_TEAM_NAME_MAP[acc]
    return clean
```

### Step 4: Refactor `teams_match`

Replace lines 367–400 of `teams_match` with the guarded algorithm:

```python
def teams_match(name1: str, name2: str) -> bool:
    """Robust fuzzy matching for team names across data providers and accent variations."""
    if not name1 or not name2 or not isinstance(name1, str) or not isinstance(name2, str):
        return False
    norm1 = normalize_team_name(name1)
    norm2 = normalize_team_name(name2)
    if norm1 and norm2 and norm1 == norm2:
        return True
    c1 = strip_accents(norm1)
    c2 = strip_accents(norm2)
    if c1 == c2:
        return True

    # Normalize delimiters
    for delim in ["-", "/", "&", ".", ","]:
        c1 = c1.replace(delim, " ")
        c2 = c2.replace(delim, " ")

    # Strip noise terms
    for noise in [" cf", " fc", " rc", " rcd", " sc", " as", " ac", " ud", " sd", " cd", " de la", " de"]:
        c1 = c1.replace(noise, " ")
        c2 = c2.replace(noise, " ")
    c1 = " ".join(c1.split())
    c2 = " ".join(c2.split())

    if c1 == c2:
        return True

    # NOTE: Unanchored substring matching (c1 in c2 or c2 in c1) is deliberately REMOVED
    # to prevent collisions between distinct sovereign states (Niger/Nigeria, Dominica/Dominican Republic).

    w1 = set(c1.split())
    w2 = set(c2.split())
    if not w1 or not w2:
        return False

    # 1. Guard Directional Tokens
    NORTH_TOKENS = {"north", "northern"}
    SOUTH_TOKENS = {"south", "southern"}
    EAST_TOKENS = {"east", "eastern"}
    WEST_TOKENS = {"west", "western"}
    ALL_DIRECTIONAL = NORTH_TOKENS | SOUTH_TOKENS | EAST_TOKENS | WEST_TOKENS | {"central", "equatorial"}

    has_north1, has_north2 = bool(w1 & NORTH_TOKENS), bool(w2 & NORTH_TOKENS)
    has_south1, has_south2 = bool(w1 & SOUTH_TOKENS), bool(w2 & SOUTH_TOKENS)
    if (has_north1 and has_south2) or (has_south1 and has_north2):
        return False

    has_east1, has_east2 = bool(w1 & EAST_TOKENS), bool(w2 & EAST_TOKENS)
    has_west1, has_west2 = bool(w1 & WEST_TOKENS), bool(w2 & WEST_TOKENS)
    if (has_east1 and has_west2) or (has_west1 and has_east2):
        return False

    # Asymmetric directional qualifiers (e.g. Sudan vs South Sudan, Guinea vs Equatorial Guinea)
    if (w1 & ALL_DIRECTIONAL) != (w2 & ALL_DIRECTIONAL):
        return False

    # 2. Guard Specific Distinguishing Qualifiers
    # DR Congo vs Congo, Korea DPR vs Korea Republic
    DR_TOKENS = {"dr", "democratic", "dpr"}
    if bool(w1 & DR_TOKENS) != bool(w2 & DR_TOKENS):
        return False

    # Guinea-Bissau vs Guinea
    if ("bissau" in w1) != ("bissau" in w2):
        return False

    # 3. Guard Conflicting Club Qualifiers (e.g. Manchester City vs Manchester United)
    CLUB_QUALIFIERS = {
        "city", "united", "town", "rovers", "wanderers", "albion",
        "county", "athletic", "atletico", "ath", "real", "sporting",
        "deportivo", "inter", "forest", "wednesday", "hotspur", "orient",
        "cercle", "club",
    }
    q1 = w1 & CLUB_QUALIFIERS
    q2 = w2 & CLUB_QUALIFIERS
    if q1 and q2 and not (q1 & q2):
        return False

    # 4. Filter Overlap Against Comprehensive Stop Words
    STOP_WORDS = {
        # Club qualifiers
        "real", "club", "atletico", "athletic", "ath", "sporting", "city", "united", "town",
        "county", "rovers", "wanderers", "albion", "deportivo", "hotspur", "orient",
        "forest", "wednesday", "cercle",
        # Prefixes / suffixes
        "man", "manchester", "fc", "cf", "afc", "sc", "ac", "cd", "ud", "sd",
        "saint", "st", "san", "santa",
        # Prepositions / articles
        "de", "la", "del", "of", "and", "the", "le", "les", "el", "al",
        # Political / sovereign / geographical qualifiers
        "republic", "rep", "democratic", "dr", "dpr", "state", "states", "federation",
        "island", "islands", "isle", "north", "northern", "south", "southern",
        "east", "eastern", "west", "western", "central", "equatorial",
    }

    overlap = w1.intersection(w2)
    meaningful_overlap = overlap - STOP_WORDS
    if meaningful_overlap:
        w1_non_noise = w1 - STOP_WORDS
        w2_non_noise = w2 - STOP_WORDS
        if meaningful_overlap == w1_non_noise or meaningful_overlap == w2_non_noise:
            return True
        if len(meaningful_overlap) >= 2:
            return True
    return False
```

---

## 5. Verification Method

Once Worker 1 applies the changes, verify using the following commands:

```bash
# 1. Run full adversarial suite
PYTHONPATH=".:Football" .venv/bin/python -m unittest tests/test_milestone1_adversarial.py -v

# 2. Run independent defect check script
PYTHONPATH=".:Football" .venv/bin/python -c "
from football_core.utils.helpers import normalize_team_name, teams_match

# Verify Bosnia
assert normalize_team_name('Bosnia') == 'Bosnia and Herzegovina'
assert normalize_team_name('bosnia') == 'Bosnia and Herzegovina'

# Verify Case-Insensitivity
assert normalize_team_name('usa') == 'United States'
assert normalize_team_name('czechia') == 'Czech Republic'
assert normalize_team_name(\"cote d'ivoire\") == 'Ivory Coast'
assert teams_match('usa', 'United States') is True
assert teams_match('czechia', 'Czech Republic') is True
assert teams_match(\"cote d'ivoire\", 'Ivory Coast') is True

# Verify Negative Pairs (All MUST be False)
neg_pairs = [
    ('Niger', 'Nigeria'),
    ('South Korea', 'North Korea'),
    ('Korea Republic', 'Korea DPR'),
    ('Republic of Ireland', 'Northern Ireland'),
    ('Ireland', 'Northern Ireland'),
    ('Congo', 'DR Congo'),
    ('Democratic Republic of the Congo', 'Congo'),
    ('Sudan', 'South Sudan'),
    ('Guinea', 'Guinea-Bissau'),
    ('Guinea', 'Equatorial Guinea'),
    ('Guinea-Bissau', 'Equatorial Guinea'),
    ('Dominica', 'Dominican Republic'),
    ('Manchester City', 'Manchester United'),
    ('Man City', 'Man United'),
    ('Central African Republic', 'South Africa'),
    ('Real Madrid', 'Atletico Madrid'),
    ('Athletic Bilbao', 'Atletico Madrid'),
    ('Sheffield United', 'Sheffield Wednesday'),
    ('Bristol City', 'Bristol Rovers'),
    ('Cercle Brugge', 'Club Brugge'),
]
for t1, t2 in neg_pairs:
    assert not teams_match(t1, t2), f'Collision detected: {t1} == {t2}'

print('ALL HELPERS REMEDIATION ASSERTIONS PASSED!')
"
```
