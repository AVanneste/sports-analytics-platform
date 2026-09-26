## 2026-09-26T09:26:05Z
You are Explorer 3 for Milestone 1: Data Source Integration & League Config.
Working directory: /home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_m1_config/
Authoritative request file: /home/antoine/Code/AG_sports_data/.agents/teamwork/ORIGINAL_REQUEST.md (read this first).
Project blueprint file: /home/antoine/Code/AG_sports_data/PROJECT.md
Survey findings: /home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_survey_data/handoff.md
Strict rules: Read and follow .agents/rules/strict-grounding.md. NEVER invent, fabricate, or simulate any data, scores, odds, fixtures, or match results.

Your specific focus for Milestone 1:
Inspect Football/football_core/config.py and Football/football_core/utils/helpers.py:
1. Examine LEAGUES in config.py and define the full dictionary entries for all 10 international tournaments (UEFA Nations League, FIFA World Cup, Qualifiers UEFA/CONMEBOL/CAF, UEFA Euro, Copa América, AFCON, Friendlies, Gold Cup) with appropriate flags, is_cup: True, is_international: True, odds_key: None, and canonical ESPN codes.
2. Examine helpers.py and define the national team name normalization mapping between ESPN and the historical dataset.
3. Check interactions with domestic downloaders (fetcher.py, auto_update.py) to guarantee they ignore is_cup competitions.
4. Formulate the precise implementation strategy for Worker. Do NOT write the implementation code to source files.
5. Write your handoff report to /home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_m1_config/handoff.md and send a message to parent.
