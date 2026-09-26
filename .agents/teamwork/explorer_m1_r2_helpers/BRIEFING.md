# BRIEFING — 2026-09-26T13:25:30Z

## Mission
Investigate false-positive collisions, case-insensitivity, alias mapping, and formulate an exact fix strategy for teams_match and normalize_team_name in Football/football_core/utils/helpers.py.

## 🔒 My Identity
- Archetype: explorer
- Roles: investigation, synthesis
- Working directory: /home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_m1_r2_helpers/
- Original parent: 46f6f8cd-21b3-4356-b686-bf78b91e125f
- Milestone: Milestone 1 Iteration 2 (Remediation)

## 🔒 Key Constraints
- Read-only investigation — do NOT implement code directly
- Strictly follow .agents/rules/strict-grounding.md
- Zero tolerance for hallucination; rely exclusively on real codebase and verified documentation

## Current Parent
- Conversation ID: 46f6f8cd-21b3-4356-b686-bf78b91e125f
- Updated: 2026-09-26T13:20:52Z

## Investigation State
- **Explored paths**:
  - `Football/football_core/utils/helpers.py` (`TEAM_NAME_MAP`, `NATIONAL_TEAM_MAP`, `teams_match`, `normalize_team_name`)
  - `tests/test_milestone1_adversarial.py`, `tests/test_adversarial_m1.py`
  - `.agents/teamwork/orchestrator/GATE_STATUS.md`, `reviewer_m1_2/handoff.md`, `challenger_m1_2/handoff.md`
  - `Football/data/raw/International/results.csv`
- **Key findings**:
  - Unanchored substring matching `(c1 in c2 or c2 in c1)` in `helpers.py:389` causes cross-entity collisions (`Niger`/`Nigeria`, `Dominica`/`Dominican Republic`, `Mali`/`Somalia`, `Oman`/`Romania`). Must be eliminated completely.
  - Single-token overlap in line 396 without directional or qualifying guards collides `South Korea`/`North Korea`, `Republic of Ireland`/`Northern Ireland`, `Sudan`/`South Sudan`, `Congo`/`DR Congo`, `Guinea`/`Guinea-Bissau`/`Equatorial Guinea`, `Manchester City`/`Manchester United`.
  - Missing stop words: `"man"`, `"manchester"`, `"ath"`, `"cercle"`, `"forest"`, etc.
  - Case-sensitivity gap: `normalize_team_name` does exact dict lookup without `.lower()`, failing `'usa'`, `'czechia'`, `'cote d\'ivoire'`.
  - Missing standalone alias: `'Bosnia'` is absent from `NATIONAL_TEAM_MAP`, while `results.csv` canonical name is `'Bosnia and Herzegovina'`.
- **Unexplored areas**: None. Remediation scope fully mapped and empirically verified via prototyping.

## Key Decisions Made
- Formulated 5-part remediation strategy for Worker 1:
  1. Add `'Bosnia': 'Bosnia and Herzegovina'` and `'United States': 'United States'` to `NATIONAL_TEAM_MAP` and `NATIONAL_TEAM_ALIASES`.
  2. Implement `_LOWER_TEAM_NAME_MAP` for case- and accent-insensitive canonical resolution in `normalize_team_name`.
  3. Remove unanchored substring matching `(c1 in c2 or c2 in c1)` entirely from `teams_match`.
  4. Guard directional and distinguishing qualifiers (opposing directions, asymmetric directional modifiers, DR/democratic, Bissau, and club qualifiers).
  5. Expand stop words list and require meaningful (non-stop) overlap.

## Artifact Index
- /home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_m1_r2_helpers/DISPATCH.md — Initial dispatch message
- /home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_m1_r2_helpers/BRIEFING.md — Persistent context
- /home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_m1_r2_helpers/progress.md — Liveness heartbeat
- /home/antoine/Code/AG_sports_data/.agents/teamwork/explorer_m1_r2_helpers/handoff.md — 5-component handoff report
