# Progress — Explorer 1 (helpers.py remediation)

- **Status**: Investigation and fix strategy formulation complete
- **Last visited**: 2026-09-26T13:25:00Z
- **Completed**:
  - Inspected `Football/football_core/utils/helpers.py`, `GATE_STATUS.md`, `reviewer_m1_2/handoff.md`, `challenger_m1_2/handoff.md`, and test suites.
  - Analyzed root causes for all 8 false-positive collision pairs:
    1. `Niger` vs `Nigeria`: unanchored substring matching (`c1 in c2`).
    2. `South Korea` vs `North Korea`: single token overlap on `"korea"`, opposing directional tokens (`"south"` vs `"north"`).
    3. `Republic of Ireland` vs `Northern Ireland`: token overlap on `"ireland"`, asymmetric directional token (`"northern"`).
    4. `Congo` vs `DR Congo`: substring and token overlap on `"congo"`, asymmetric state qualifier (`"dr"` / `"democratic"`).
    5. `Sudan` vs `South Sudan`: substring and token overlap on `"sudan"`, asymmetric directional token (`"south"`).
    6. `Guinea` vs `Guinea-Bissau` / `Equatorial Guinea`: substring and token overlap on `"guinea"`, distinguishing qualifiers (`"bissau"`, `"equatorial"`).
    7. `Dominica` vs `Dominican Republic`: unanchored substring matching (`"dominica"` inside `"dominican"`).
    8. `Manchester City` vs `Manchester United`: token overlap on unstopped `"man"` / `"manchester"`, conflicting club qualifiers (`"city"` vs `"united"`).
  - Analyzed case-sensitivity gap in `normalize_team_name` (`"usa"`, `"czechia"`, `"cote d'ivoire"` returning unmapped).
  - Confirmed missing `"Bosnia": "Bosnia and Herzegovina"` mapping in `NATIONAL_TEAM_MAP`.
  - Tested and verified proposed modular fix logic against all 16+ negative pairs, all 55+ positive variation pairs, and 19,500+ canonical team pairs.
- **Current task**: Writing comprehensive handoff report to `handoff.md`.
