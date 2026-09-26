# BRIEFING — 2026-09-26T09:22:30Z

## Mission
Investigate ESPN client endpoints, odds parsing, odds_api fallback mechanics, and international football league configurations in config.py.

## 🔒 My Identity
- Archetype: explorer
- Roles: Data Sources & Config Explorer
- Working directory: /home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_survey_data/
- Original parent: 46f6f8cd-21b3-4356-b686-bf78b91e125f
- Milestone: Investigation and architecture analysis for data sources and international football config

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Strict Grounding: NEVER invent, fabricate, or simulate any data, scores, odds, fixtures, or match results. Only rely on real and verifiable data present in workspace or official documentation / tool outputs.
- Write only to /home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_survey_data/

## Current Parent
- Conversation ID: 46f6f8cd-21b3-4356-b686-bf78b91e125f
- Updated: 2026-09-26T09:13:18Z

## Investigation State
- **Explored paths**:
  - `Football/football_core/config.py`: Inspected `LEAGUES` dict; currently has 9 domestic + 3 European cups; missing all international competitions and `is_international` flags.
  - `Football/football_core/data/espn_client.py`: Inspected `ESPN_BASE_URL`, endpoints, DraftKings moneyline/totals parsing, scoreboard query loops, boxscore reconciliation.
  - `Football/football_core/data/odds_api.py`: Inspected quota checking, HTTP 401 handling, ESPN fallback triggers, and multi-league iteration bottlenecks.
  - `Football/football_core/data/api_football.py`: Inspected fixture date search and boxscore reconciliation logic; verified international team matching.
  - `Football/football_core/utils/helpers.py`: Inspected `TEAM_NAME_MAP` and `teams_match`; tested national team matching; identified key missing aliases (USA, Côte d'Ivoire, Czechia, Türkiye, Bosnia-Herzegovina).
  - `Football/football_core/models/predictor.py`: Inspected bundle loading and cup/cross-league fallback logic.
  - `Football/data/raw/International/results.csv`: Verified real dataset containing 49,547 matches (1872-2026), 8,247 matches from 2018-2026 covering all required tournaments.
  - `Football/data/cache/predictions_tracker.json`: Verified 203 settled matches intact.
  - `web/src/types.ts` & `web/src/App.tsx`: Verified dynamic league pills and TypeScript compilation (`tsc --noEmit` exit 0).
- **Key findings**:
  - ESPN API endpoints use `https://site.api.espn.com/apis/site/v2/sports/soccer/{espn_code}/scoreboard` and support date ranges `dates=YYYYMMDD-YYYYMMDD` as well as gameday scoreboards.
  - Odds parsing converts American moneylines and totals into European decimals, with fallbacks needed for `EVEN`, `homeTeamOdds`/`awayTeamOdds`/`drawOdds` fields, and decimal detection.
  - In `odds_api.py`, handling `ODDS_API_KEY=invalid` requires immediate ESPN bypass when the key is falsy/invalid or when `odds_key` is None (preventing calls to `/sports/None/odds/`), and caching failure headers immediately to avoid redundant failing requests.
  - In `config.py`, 10 international competitions must be registered with `is_cup: True`, `is_international: True`, `flag`, and `espn_code`.
- **Unexplored areas**: None for data sources & config. Ready for final report.

## Key Decisions Made
- Fully cataloged all required data transformations, endpoints, and configs.
- Detailed step-by-step architecture proposal and patch plan for implementer.

## Artifact Index
- DISPATCH.md — Received dispatch message
- BRIEFING.md — Persistent working memory
- progress.md — Liveness heartbeat
- handoff.md — Comprehensive exploration and architecture report
