## 2026-09-26T13:20:52Z
You are Explorer 1 for Milestone 1 Iteration 2 (Remediation).
Working directory: /home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_m1_r2_helpers/
Authoritative request file: /home/antoine/Code/AG_sports_data/.agents/teamwork/ORIGINAL_REQUEST.md (read this first).
Project blueprint file: /home/antoine/Code/AG_sports_data/PROJECT.md
Gate failure details: /home/antoine/Code/AG_sports_data/.agents/teamwork/orchestrator/GATE_STATUS.md
Reviewer 2 feedback: /home/antoine/Code/AG_sports_data/.agents/teamwork/reviewer_m1_2/handoff.md
Challenger 2 feedback: /home/antoine/Code/AG_sports_data/.agents/teamwork/challenger_m1_2/handoff.md
Strict rules: Read and follow .agents/rules/strict-grounding.md.

Your mission:
Inspect Football/football_core/utils/helpers.py:
1. Review the false-positive collisions identified by Reviewer 2 and Challenger 2:
   - Niger vs Nigeria -> False
   - South Korea vs North Korea -> False
   - Republic of Ireland vs Northern Ireland -> False
   - Congo vs DR Congo -> False
   - Sudan vs South Sudan -> False
   - Guinea vs Guinea-Bissau / Equatorial Guinea -> False
   - Dominica vs Dominican Republic -> False
   - Manchester City vs Manchester United -> False
2. Review case-insensitivity in normalize_team_name (e.g. 'usa', 'czechia' must resolve to canonical names).
3. Ensure 'Bosnia' maps to 'Bosnia and Herzegovina'.
4. Formulate the exact fix strategy for teams_match and normalize_team_name (guarding directional and qualifying tokens, updating stop-words, preventing naive substring matching). Do NOT implement code directly.
5. Write your handoff report to /home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_m1_r2_helpers/handoff.md and message parent.
