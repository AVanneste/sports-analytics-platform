# Handoff Report: Explorer 3 — Milestone 1 Iteration 2 (ESPN Client Remediation)

**Agent**: Explorer 3 (`explorer_m1_r2_espn`)  
**Mission**: Investigate `Football/football_core/data/espn_client.py` issues and formulate exact fix strategy for Worker.  
**Working Directory**: `/home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_m1_r2_espn/`  
**Patch Files**:
- `/home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_m1_r2_espn/proposed_espn_client.patch`
- `/home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_m1_r2_espn/proposed_test_adversarial_m1.patch`

---

## 1. Observation

### 1.1 Missing Contract Field `"bookmaker": "DraftKings (ESPN)"`
- **Location**: `Football/football_core/data/espn_client.py`, lines 242–266.
- **Contract Specification**: `PROJECT.md`, Interface Contract 2:
  ```markdown
  ### 2. `espn_client.py` ↔ Upcoming Fixture Consumers
  - `fetch_espn_upcoming_fixtures(league_key: str, days_ahead: int = 14) -> List[Dict[str, Any]]`:
    Returns list of dicts:
    ...
    - `bookmaker`: "DraftKings (ESPN)"
    - `is_neutral`: bool
  ```
- **Observed Code**:
  Lines 242–266 of `Football/football_core/data/espn_client.py`:
  ```python
  fixtures.append({
      "match_id": match_id,
      "espn_id": e.get("id"),
      "league": league_key,
      "league_name": league_info.get("name", league_key),
      "flag": league_info.get("flag", "⚽"),
      "date": date_str,
      "commence_time": date_iso,
      "home_team": home_norm,
      "away_team": away_norm,
      "referee": referee_name,
      "is_neutral": bool(comp.get("neutralSite", False)),
      "odds_home": odds_h,
      "odds_draw": odds_d,
      ...
  })
  ```
  The payload omits `"bookmaker": "DraftKings (ESPN)"`.

### 1.2 Non-Finite Values in `american_to_decimal`
- **Location**: `Football/football_core/data/espn_client.py`, lines 78–105.
- **Observed Behavior**:
  Executing `american_to_decimal` with non-finite values yielded:
  ```python
  american_to_decimal(float('inf'))  # -> returns inf (float)
  american_to_decimal('inf')         # -> returns inf (float)
  american_to_decimal(float('-inf')) # -> returns 1.0 (float)
  american_to_decimal('-inf')        # -> returns 1.0 (float)
  ```
  In lines 96–99:
  ```python
  if val >= 100.0:
      return round(1.0 + (val / 100.0), 2)
  elif val <= -100.0:
      return round(1.0 + (100.0 / abs(val)), 2)
  ```
  `inf >= 100.0` evaluates to `True`, producing `inf`. `-inf <= -100.0` evaluates to `True`, and `1.0 + (100.0 / abs(-inf))` evaluates to `1.0 + 0.0 = 1.0`. Neither `inf` nor `1.0` are valid betting odds. `import math` is currently absent from `espn_client.py`.

### 1.3 `IndexError` on Empty `competitions: []`
- **Location**: `Football/football_core/data/espn_client.py`, lines 156, 292, 429, 555.
- **Observed Code**:
  ```python
  comp = e.get("competitions", [{}])[0]
  ```
  When an event dictionary from ESPN contains `"competitions": []`, `e.get("competitions", [{}])` returns `[]` (because the key exists, so the default `[{}]` is not used). Subscripting `[][0]` immediately raises:
  `IndexError: list index out of range`.
- **Test Invariant Observed**:
  `tests/test_adversarial_m1.py`, lines 335–344:
  ```python
  @patch("football_core.data.espn_client._espn_get_json")
  def test_espn_empty_competitions_vulnerability(self, mock_espn_get):
      """Document vulnerability: if ESPN returns an event shell with 'competitions': [], IndexError is raised."""
      mock_espn_get.return_value = {
          "events": [
              {"id": "bad_event_shell", "competitions": []}
          ]
      }
      with self.assertRaises(IndexError):
          fetch_espn_upcoming_fixtures("EPL")
  ```
  This existing test explicitly asserts that `fetch_espn_upcoming_fixtures` raises `IndexError`. Once the vulnerability is guarded, this test will fail unless updated to assert that it returns `[]` safely.

### 1.4 `AttributeError` on `None` Subdicts During Odds Parsing
- **Location**: `Football/football_core/data/espn_client.py`, lines 193–239.
- **Observed Code**:
  ```python
  ml = o_item.get("moneyline", {}) or {}
  if ml:
      odds_h = american_to_decimal(ml.get("home", {}).get("close", {}).get("odds") or ml.get("home", {}).get("open", {}).get("odds"))
  ```
  When ESPN provides an item where `"moneyline"` has `"home": None`, `ml.get("home", {})` evaluates to `None` (key is present, default `{}` is skipped). Chaining `.get("close", {})` on `None` raises:
  `AttributeError: 'NoneType' object has no attribute 'get'`.
  Similarly, if `ml.get("home")` has `{"close": None}`, `.get("close", {}).get("odds")` fails with `AttributeError`.
  The identical vulnerability exists for `tot.get("over", {}).get("close", {})` (lines 223–224) and fallback lines 205, 211, 217, 230, 236 (`ht_odds.get("close", {}).get("odds")`, etc.).

---

## 2. Logic Chain

1. **Premise 1 (Contract Conformance)**: Downstream consumers (frontend, exporter, tracker) rely on the interface contract in `PROJECT.md` Section 2.
   - *Observation*: `PROJECT.md` specifies `"bookmaker": "DraftKings (ESPN)"`. Line 242 of `espn_client.py` omits it.
   - *Inference*: Adding `"bookmaker": "DraftKings (ESPN)"` to the fixture dict fulfills the interface specification with zero side effects.

2. **Premise 2 (Numeric Robustness)**: External or malformed input must never inject non-finite values (`inf`, `-inf`, `nan`) into odds calculations or JSON serializers.
   - *Observation*: `american_to_decimal(float('inf'))` returns `inf`; `american_to_decimal(float('-inf'))` returns `1.0`.
   - *Inference*: Checking `not math.isfinite(val)` immediately after `val = float(val_str)` ensures `inf`, `-inf`, and `nan` cleanly return `None`.

3. **Premise 3 (Event Resilience)**: ESPN API event responses occasionally contain empty competition shells (`"competitions": []`).
   - *Observation*: `[][0]` raises `IndexError`.
   - *Inference*: Checking `competitions = e.get("competitions") or []` and `if not competitions or not isinstance(competitions[0], dict): continue` cleanly ignores malformed shells.
   - *Inference (Test Coupling)*: `tests/test_adversarial_m1.py:335` tests this exact behavior by asserting `IndexError`. Remediating the code requires updating the test to assert `self.assertEqual(res, [])`.

4. **Premise 4 (Safe Nested Traversal)**: Sparse or partially null JSON payloads must not cause unhandled attribute crashes.
   - *Observation*: Python's `dict.get(key, default)` returns `None` if `key` exists and has value `None`. Chained `.get()` calls crash.
   - *Inference*: Wrapping intermediate lookups with `or {}` — specifically `((ml.get("home") or {}).get("close") or {}).get("odds")` — guarantees safe evaluation to `None` regardless of which level is `None`.

---

## 3. Caveats

- **Network Sandbox Egress**: The testing sandbox blocks live network connections to `site.api.espn.com` (HTTP 403). All behavior was verified via unit tests, synthetic mocks, and local regression harnesses.
- **Other Functions in `espn_client.py`**: Although the dispatch prompt focused on `fetch_espn_upcoming_fixtures`, `fetch_espn_completed_matches`, `reconcile_tracker_with_espn`, and `backfill_missing_corners_cards` share the same `comp = e.get("competitions", [{}])[0]` pattern. The proposed patch hardens all 4 functions to eliminate potential regressions.

---

## 4. Conclusion & Exact Fix Strategy

Worker 1 should apply the following exact changes to `Football/football_core/data/espn_client.py` and `tests/test_adversarial_m1.py`.

### Fix 1: Add `import math` to `espn_client.py`
**File**: `Football/football_core/data/espn_client.py` (Line 8)
```python
import json
import logging
import math
import subprocess
import time
```

### Fix 2: Add `math.isfinite(val)` Check in `american_to_decimal`
**File**: `Football/football_core/data/espn_client.py` (Lines 89–95)
```python
    try:
        val = float(val_str)
        if not math.isfinite(val):
            return None
        if val == 0:
            return None
```

### Fix 3: Guard Empty `competitions: []` in `fetch_espn_upcoming_fixtures` (and Sibling Functions)
**File**: `Football/football_core/data/espn_client.py` (Lines 155–163)
```python
    for e in events:
        competitions = e.get("competitions") or []
        if not competitions or not isinstance(competitions[0], dict):
            continue
        comp = competitions[0]
        status_info = (comp.get("status") or {}).get("type") or {}
        if status_info.get("completed", False):
            continue  # Skip finished games
```
*(Apply the same pattern to lines 291–296, 428–432, and 554–558).*

### Fix 4: Guard Nested Odds Lookups Against `None` Subdicts
**File**: `Football/football_core/data/espn_client.py` (Lines 193–240)
```python
        if odds_list and isinstance(odds_list[0], dict):
            o_item = odds_list[0]
            ml = o_item.get("moneyline") or {}
            if isinstance(ml, dict) and ml:
                odds_h = american_to_decimal(
                    ((ml.get("home") or {}).get("close") or {}).get("odds")
                    or ((ml.get("home") or {}).get("open") or {}).get("odds")
                )
                odds_d = american_to_decimal(
                    ((ml.get("draw") or {}).get("close") or {}).get("odds")
                    or ((ml.get("draw") or {}).get("open") or {}).get("odds")
                )
                odds_a = american_to_decimal(
                    ((ml.get("away") or {}).get("close") or {}).get("odds")
                    or ((ml.get("away") or {}).get("open") or {}).get("odds")
                )
            
            # Moneyline fallbacks when ml is sparse
            if odds_h is None and o_item.get("homeTeamOdds"):
                ht_odds = o_item.get("homeTeamOdds")
                if isinstance(ht_odds, dict):
                    odds_h = american_to_decimal(
                        ht_odds.get("moneyLine")
                        or (ht_odds.get("close") or {}).get("odds")
                        or ht_odds.get("odds")
                    )
                else:
                    odds_h = american_to_decimal(ht_odds)
            if odds_a is None and o_item.get("awayTeamOdds"):
                at_odds = o_item.get("awayTeamOdds")
                if isinstance(at_odds, dict):
                    odds_a = american_to_decimal(
                        at_odds.get("moneyLine")
                        or (at_odds.get("close") or {}).get("odds")
                        or at_odds.get("odds")
                    )
                else:
                    odds_a = american_to_decimal(at_odds)
            if odds_d is None and o_item.get("drawOdds"):
                dr_odds = o_item.get("drawOdds")
                if isinstance(dr_odds, dict):
                    odds_d = american_to_decimal(
                        dr_odds.get("moneyLine")
                        or (dr_odds.get("close") or {}).get("odds")
                        or dr_odds.get("odds")
                    )
                else:
                    odds_d = american_to_decimal(dr_odds)

            tot = o_item.get("total") or {}
            if isinstance(tot, dict) and tot:
                odds_o25 = american_to_decimal(
                    ((tot.get("over") or {}).get("close") or {}).get("odds")
                    or ((tot.get("over") or {}).get("open") or {}).get("odds")
                )
                odds_u25 = american_to_decimal(
                    ((tot.get("under") or {}).get("close") or {}).get("odds")
                    or ((tot.get("under") or {}).get("open") or {}).get("odds")
                )

            # Totals fallbacks when tot is sparse
            if odds_o25 is None and o_item.get("overOdds") is not None:
                o_odds = o_item.get("overOdds")
                if isinstance(o_odds, dict):
                    odds_o25 = american_to_decimal(
                        o_odds.get("moneyLine")
                        or (o_odds.get("close") or {}).get("odds")
                        or o_odds.get("odds")
                    )
                else:
                    odds_o25 = american_to_decimal(o_odds)
            if odds_u25 is None and o_item.get("underOdds") is not None:
                u_odds = o_item.get("underOdds")
                if isinstance(u_odds, dict):
                    odds_u25 = american_to_decimal(
                        u_odds.get("moneyLine")
                        or (u_odds.get("close") or {}).get("odds")
                        or u_odds.get("odds")
                    )
                else:
                    odds_u25 = american_to_decimal(u_odds)
```

### Fix 5: Include `"bookmaker": "DraftKings (ESPN)"` in Fixture Payload
**File**: `Football/football_core/data/espn_client.py` (Line 254)
```python
        fixtures.append({
            "match_id": match_id,
            "espn_id": e.get("id"),
            "league": league_key,
            "league_name": league_info.get("name", league_key),
            "flag": league_info.get("flag", "⚽"),
            "date": date_str,
            "commence_time": date_iso,
            "home_team": home_norm,
            "away_team": away_norm,
            "referee": referee_name,
            "is_neutral": bool(comp.get("neutralSite", False)),
            "bookmaker": "DraftKings (ESPN)",
            "odds_home": odds_h,
            ...
```

### Fix 6: Update `test_adversarial_m1.py` for Empty Competitions and Inf Checks
**File**: `tests/test_adversarial_m1.py`
1. In `test_infinity_and_nan` (line 109):
   ```python
   self.assertIsNone(american_to_decimal(float("inf")))
   self.assertIsNone(american_to_decimal("inf"))
   self.assertIsNone(american_to_decimal(float("-inf")))
   self.assertIsNone(american_to_decimal("-inf"))
   ```
2. In `test_espn_empty_competitions_vulnerability` (line 335):
   ```python
   @patch("football_core.data.espn_client._espn_get_json")
   def test_espn_empty_competitions_vulnerability(self, mock_espn_get):
       """Verify empty 'competitions': [] in event shell is safely skipped without IndexError."""
       mock_espn_get.return_value = {
           "events": [
               {"id": "bad_event_shell", "competitions": []}
           ]
       }
       res = fetch_espn_upcoming_fixtures("EPL")
       self.assertEqual(res, [])
   ```

---

## 5. Verification Method

Once Worker 1 applies the fixes, run the following verification suite:

```bash
# 1. Run unit test on american_to_decimal non-finite inputs and empty competitions
.venv/bin/python -c "
import sys, math
sys.path.insert(0, 'Football')
from football_core.data.espn_client import american_to_decimal, fetch_espn_upcoming_fixtures
from unittest.mock import patch

# Verify non-finite inputs return None
assert american_to_decimal(float('inf')) is None, 'inf float failed'
assert american_to_decimal('inf') is None, 'inf string failed'
assert american_to_decimal(float('-inf')) is None, '-inf float failed'
assert american_to_decimal('-inf') is None, '-inf string failed'
assert american_to_decimal(float('nan')) is None, 'nan float failed'
assert american_to_decimal('nan') is None, 'nan string failed'

# Verify empty competitions returns [] without IndexError
with patch('football_core.data.espn_client._espn_get_json') as mock_get:
    mock_get.return_value = {'events': [{'id': 'e1', 'competitions': []}]}
    res = fetch_espn_upcoming_fixtures('EPL')
    assert res == [], f'Expected [], got {res}'

# Verify bookmaker in fixture payload
with patch('football_core.data.espn_client._espn_get_json') as mock_get:
    mock_get.return_value = {
        'events': [{
            'id': 'e2',
            'competitions': [{
                'status': {'type': {'completed': False}},
                'competitors': [
                    {'homeAway': 'home', 'team': {'displayName': 'Arsenal'}},
                    {'homeAway': 'away', 'team': {'displayName': 'Chelsea'}},
                ],
                'odds': [{'moneyline': {'home': None, 'away': {'close': {'odds': '+150'}}}}]
            }]
        }]
    }
    fixtures = fetch_espn_upcoming_fixtures('EPL')
    assert len(fixtures) == 1
    assert fixtures[0]['bookmaker'] == 'DraftKings (ESPN)', 'Missing bookmaker key'
    assert fixtures[0]['odds_home'] is None, 'Null moneyline subdict failed'
    assert fixtures[0]['odds_away'] == 2.50, 'Moneyline away parsing failed'

print('ALL ESPN CLIENT REMEDIATION VERIFICATIONS PASSED!')
"

# 2. Run the test suites
.venv/bin/python -m unittest tests/test_adversarial_m1.py
.venv/bin/python -m unittest tests/test_milestone1_adversarial.py

# 3. Verify TypeScript build
cd web && npx tsc --noEmit
```
