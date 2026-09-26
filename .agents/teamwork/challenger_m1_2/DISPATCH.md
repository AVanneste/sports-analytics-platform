## 2026-09-26T13:12:45Z
You are Challenger 2 for Milestone 1: Free Data Source Integration & League Configuration.
Working directory: /home/antoine/Code/AG_sports_data/.agents/teamwork/challenger_m1_2/
Authoritative request file: /home/antoine/Code/AG_sports_data/.agents/teamwork/ORIGINAL_REQUEST.md (read this first).
Project blueprint file: /home/antoine/Code/AG_sports_data/PROJECT.md
Worker 1 handoff report: /home/antoine/Code/AG_sports_data/.agents/teamwork/worker_m1/handoff.md
Strict rules: Read and follow .agents/rules/strict-grounding.md.

Your mission:
1. Write and execute an adversarial test harness to empirically test:
   - Config integrity: verify all 22 competitions have expected keys (name, country, code, espn_code, flag, is_cup, is_international).
   - Bypassing domestic downloaders: verify that fetcher.py and auto_update.py skip competitions where is_cup is True (ensuring international competitions will never trigger domestic CSV download errors).
   - Team name normalization: test 50+ national team variations (USA, Ivory Coast, Turkey, Czechia, Bosnia, South Korea, Iran, DR Congo, Cape Verde, Ireland, etc.) against teams_match and normalize_team_name.
2. Record all empirical test results in /home/antoine/Code/AG_sports_data/.agents/teamwork/challenger_m1_2/handoff.md with an explicit verdict: APPROVE or REQUEST_CHANGES.
3. Send a message to parent summarizing your test results and verdict.
