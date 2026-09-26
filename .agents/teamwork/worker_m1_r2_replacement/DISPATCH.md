## 2026-09-26T13:37:32Z
You are Worker 2 (Replacement) for Milestone 1 Iteration 2 (Remediation).
Working directory: /home/antoine/Code/AG_sports_data/.agents/teamwork/worker_m1_r2_replacement/
Authoritative request file: /home/antoine/Code/AG_sports_data/.agents/teamwork/ORIGINAL_REQUEST.md (read this first).
Project blueprint file: /home/antoine/Code/AG_sports_data/PROJECT.md
Gate failure details: /home/antoine/Code/AG_sports_data/.agents/teamwork/orchestrator/GATE_STATUS.md
Remediation strategies and handoffs from Explorers:
- Helpers: /home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_m1_r2_helpers/handoff.md
- Odds API: /home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_m1_r2_odds/handoff.md
- ESPN Client: /home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_m1_r2_espn/handoff.md
Strict rules: Read and follow .agents/rules/strict-grounding.md.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Exclusive file write ownership:
- Football/football_core/utils/helpers.py
- Football/football_core/data/odds_api.py
- Football/football_core/data/espn_client.py
- tests/test_adversarial_m1.py
Do NOT edit other files.

Your tasks:
1. Update Football/football_core/utils/helpers.py:
   - Make normalize_team_name case-insensitive and accent-insensitive. Add 'Bosnia' -> 'Bosnia and Herzegovina'.
   - Fix teams_match to eliminate false positive collisions on sovereign nations and distinct clubs (Niger vs Nigeria, South Korea vs North Korea, Republic of Ireland vs Northern Ireland, Congo vs DR Congo, Sudan vs South Sudan, Guinea vs Guinea-Bissau/Equatorial Guinea, Dominica vs Dominican Republic, Manchester City vs Manchester United). Implement the token-based directional/qualifier guards specified in explorer_m1_r2_helpers/handoff.md.
2. Update Football/football_core/data/odds_api.py:
   - Fix line 325 boolean logic: change `(not quota.get("ok", True) and rem <= 0)` to `(not quota.get("ok", True)) or (rem <= 0)`.
   - In fetch_all_live_upcoming_fixtures, wrap per-league fetch inside individual try...except blocks so an error in one league does not abort the remaining leagues.
3. Update Football/football_core/data/espn_client.py:
   - Add `"bookmaker": "DraftKings (ESPN)"` to fixture payload dictionary in fetch_espn_upcoming_fixtures.
   - In american_to_decimal, add `math.isfinite(val)` checks to reject inf, -inf, nan.
   - Guard empty `competitions: []` against IndexError across all functions.
   - Guard nested None subdicts in moneyline and totals (`(ml.get("home") or {}).get("close")`).
4. Update tests/test_adversarial_m1.py:
   - Update tests to reflect the safe empty competition return value `[]` and verify inf/nan rejection.
5. Run verification tests:
   - Run tests/test_milestone1_adversarial.py
   - Run tests/test_adversarial_m1.py
   - Run cd web && npx tsc --noEmit
   - Verify 0 forbidden random generators and that 203 football + 200 tennis tracker entries are 100% intact.
6. Write your handoff report to /home/antoine/Code/AG_sports_data/.agents/teamwork/worker_m1_r2_replacement/handoff.md and send a message to parent.
