## 2026-09-26T13:02:01Z

You are Worker 1 for Milestone 1: Free Data Source Integration & League Configuration.
Working directory: /home/antoine/Code/AG_sports_data/.agents/teamwork/worker_m1/
Authoritative request file: /home/antoine/Code/AG_sports_data/.agents/teamwork/ORIGINAL_REQUEST.md (read this first).
Project blueprint file: /home/antoine/Code/AG_sports_data/PROJECT.md
Detailed technical blueprint & explorer findings: /home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_survey_data/handoff.md
Strict rules: Read and follow .agents/rules/strict-grounding.md. NEVER invent, fabricate, or simulate any data, scores, odds, fixtures, or match results.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Exclusive file write ownership:
- Football/football_core/config.py
- Football/football_core/data/espn_client.py
- Football/football_core/data/odds_api.py
- Football/football_core/utils/helpers.py
Do NOT edit files outside this list.

Your implementation tasks:
1. Update Football/football_core/config.py:
   - Add all 10 international tournaments:
     * UEFA Nations League (key: NationsLeague, espn_code: uefa.nations, flag: 🇪🇺, is_cup: True, is_international: True, odds_key: None)
     * FIFA World Cup (key: WorldCup, espn_code: fifa.world, flag: 🏆, is_cup: True, is_international: True, odds_key: None)
     * World Cup Qualifiers UEFA (key: WCQ_UEFA, espn_code: fifa.worldq.uefa, flag: 🇪🇺, is_cup: True, is_international: True, odds_key: None)
     * World Cup Qualifiers CONMEBOL (key: WCQ_CONMEBOL, espn_code: fifa.worldq.conmebol, flag: 🌎, is_cup: True, is_international: True, odds_key: None)
     * World Cup Qualifiers CAF (key: WCQ_CAF, espn_code: fifa.worldq.caf, flag: 🌍, is_cup: True, is_international: True, odds_key: None)
     * UEFA Euro (key: Euro, espn_code: uefa.euro, flag: 🇪🇺, is_cup: True, is_international: True, odds_key: None)
     * CONMEBOL Copa America (key: CopaAmerica, espn_code: conmebol.america, flag: 🌎, is_cup: True, is_international: True, odds_key: None)
     * CAF AFCON (key: AFCON, espn_code: caf.nations, flag: 🌍, is_cup: True, is_international: True, odds_key: None)
     * International Friendlies (key: Friendlies, espn_code: fifa.friendly, flag: 🤝, is_cup: True, is_international: True, odds_key: None)
     * CONCACAF Gold Cup (key: GoldCup, espn_code: concacaf.gold, flag: 🏆, is_cup: True, is_international: True, odds_key: None)
   - Ensure existing domestic leagues and European cups are unchanged.

2. Update Football/football_core/data/espn_client.py:
   - Update ESPN_LEAGUE_CODES to include all 10 international competition keys mapped to their ESPN codes.
   - Enhance american_to_decimal to handle "EVEN", already-decimal numbers, and invalid strings.
   - Enhance fetch_espn_upcoming_fixtures:
     * Check homeTeamOdds/awayTeamOdds/drawOdds as fallbacks when DraftKings moneyline is sparse.
     * Check overOdds/underOdds as fallbacks for totals.
     * Support date range querying ("dates": f"{start_d}-{end_d}") or efficient iteration.

3. Update Football/football_core/data/odds_api.py:
   - Quota & fallback hardening:
     * Check get_stored_quota() or if ODDS_API_KEY is missing/invalid/empty or if odds_key is None -> immediately route to fetch_espn_upcoming_fixtures without making HTTP requests.
     * Handle HTTP 401/403/422/429 gracefully by saving ok: false, remaining: 0 into quota cache and falling back immediately to ESPN.
     * Verify fetch_all_live_upcoming_fixtures iterates across all configured leagues and falls back seamlessly.

4. Update Football/football_core/utils/helpers.py:
   - Add national team normalization dictionary mapping ESPN names (e.g., "United States", "Ivory Coast", "Czech Republic", "Turkey", "Bosnia and Herzegovina") to results.csv canonical names ("USA", "Côte d'Ivoire", "Czechia", "Türkiye", "Bosnia-Herzegovina").
   - Provide helper normalize_team_name(name: str) -> str.

5. Test and verify your changes:
   - Run python commands to verify ESPN fetches fixtures for NationsLeague, EPL, etc.
   - Test that ODDS_API_KEY=invalid runs fetch_league_odds and fetch_all_live_upcoming_fixtures without throwing errors and returns real ESPN fixtures.
   - Ensure no regressions.

6. Document all changes and test outputs in /home/antoine/Code/AG_sports_data/.agents/teamwork/worker_m1/handoff.md, and message parent.
