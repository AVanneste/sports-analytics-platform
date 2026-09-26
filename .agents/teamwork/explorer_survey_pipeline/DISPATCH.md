## 2026-09-26T09:13:18Z
You are the Pipeline & Web Export Explorer.
Working directory: /home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_survey_pipeline/
Authoritative request file: /home/antoine/Code/AG_sports_data/.agents/teamwork/ORIGINAL_REQUEST.md (read this first).
Strict rules: Read and follow .agents/rules/strict-grounding.md. NEVER invent, fabricate, or simulate any data, scores, odds, fixtures, or match results.

Your mission:
1. Read /home/antoine/Code/AG_sports_data/.agents/teamwork/ORIGINAL_REQUEST.md.
2. Inspect:
   - scripts/run_daily_pipeline.py: How the daily pipeline runs (fetch -> predict -> track -> reconcile -> retrain -> export), how leagues are iterated over, how model predictions are generated, how trackers are updated.
   - Football/football_core/betting/tracker.py: How predictions are tracked and reconciled, where tracker files are saved.
   - Check existing tracker files (verify the 203 football tracker entries and 200 tennis tracker entries mentioned in the request, where they reside, and how to guarantee zero regression).
   - scripts/export_web_data.py: How web/public/data/sports_data.json is generated, schema, how international fixtures and predictions need to be included.
   - web/: React/Vite/Tailwind app structure, types (src/types/ etc.), UI components for displaying leagues, filters, navigation, odds display, and verify how cd web && npx tsc --noEmit checks the frontend.
3. Write your comprehensive exploration and pipeline/web integration report to /home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_survey_pipeline/handoff.md.
4. Send a message to your parent (parent) summarizing your findings and linking to your handoff file.
