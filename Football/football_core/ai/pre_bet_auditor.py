"""Automated Pre-Bet AI Auditor for Football Matches.
Evaluates quantitative model picks with qualitative risk analysis (rest fatigue,
tactical mismatches, line traps, referee profiles) using Gemini 3.6 Flash with
a resilient local heuristic fallback.
"""
import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

def get_gemini_api_key() -> Optional[str]:
    """Retrieve Gemini API key from environment, .env file, or Streamlit secrets."""
    k = os.environ.get("GEMINI_API_KEY")
    if k and k.strip():
        return k.strip()
    # Check .env file
    env_file = Path(__file__).resolve().parents[3] / ".env"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEY="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            return val
        except Exception:
            pass
    # Check streamlit secrets
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
            return str(st.secrets["GEMINI_API_KEY"]).strip()
    except Exception:
        pass
    return None


def _local_heuristic_audit(match: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic qualitative rule-based audit when LLM is unavailable or offline."""
    home = match.get("home_team", "Home")
    away = match.get("away_team", "Away")
    pick = match.get("best_pick") or {}
    selection = pick.get("selection", f"{home} Win")
    odds = float(pick.get("odds") or match.get("odds_home") or 2.0)
    ev_val = float(pick.get("ev") or match.get("ev_edge") or 0.0)
    ev_pct = round(ev_val * 100.0, 1)

    h_elo = float(match.get("home_elo", 1500))
    a_elo = float(match.get("away_elo", 1500))
    elo_diff = h_elo - a_elo

    ref = match.get("referee") or {}
    ref_strict = (ref.get("strictness_label") or "").lower()

    pros = []
    risks = []
    confidence = 70

    # 1. EV & Probability Value Angle
    if ev_pct >= 8.0:
        pros.append(f"Exceptional mathematical edge: +{ev_pct}% EV over consensus market line.")
        confidence += 8
    elif ev_pct >= 3.0:
        pros.append(f"Solid +EV margin (+{ev_pct}%) confirming positive expected return.")
        confidence += 4
    else:
        risks.append(f"Narrow value margin (+{ev_pct}% EV) vulnerable to line shifts.")
        confidence -= 5

    # 2. Elo & Strength Rating
    if "home" in selection.lower() or home in selection:
        if elo_diff >= 80:
            pros.append(f"{home} holds substantial qualitative class advantage (+{int(elo_diff)} Elo).")
            confidence += 6
        elif elo_diff <= -50:
            risks.append(f"{home} is rated lower in fundamental Elo (-{abs(int(elo_diff))}) despite home pitch.")
            confidence -= 7
    elif "away" in selection.lower() or away in selection:
        if elo_diff <= -80:
            pros.append(f"{away} holds superior squad quality (+{abs(int(elo_diff))} Elo differential).")
            confidence += 6
        elif elo_diff >= 50:
            risks.append(f"Playing away against a fundamentally higher-rated opponent (+{int(elo_diff)} Home Elo).")
            confidence -= 8

    # 3. Market Type Nuances
    if "over" in selection.lower():
        xg_sum = float(match.get("expected_goals_home", 1.3)) + float(match.get("expected_goals_away", 1.1))
        if xg_sum >= 2.9:
            pros.append(f"Aggressive open tactical profile: Model projects {xg_sum:.2f} combined expected goals.")
        else:
            risks.append(f"Projected match total ({xg_sum:.2f} xG) leaves slim margin for Over 2.5 hit.")
            confidence -= 4
    elif "under" in selection.lower():
        xg_sum = float(match.get("expected_goals_home", 1.3)) + float(match.get("expected_goals_away", 1.1))
        if xg_sum <= 2.2:
            pros.append(f"Low-scoring structural dynamics: Projected total of only {xg_sum:.2f} xG.")
        else:
            risks.append(f"Total xG projection ({xg_sum:.2f}) presents moderate volatility against Under pick.")

    # 4. Referee Factor
    if "cards" in selection.lower() or "over 3.5 cards" in selection.lower():
        if "strict" in ref_strict or "high" in ref_strict:
            pros.append(f"Referee {ref.get('name', 'Official')} is notoriously strict ({ref.get('strictness_label')}).")
            confidence += 5
        elif "lenient" in ref_strict or "low" in ref_strict:
            risks.append(f"Appointed referee {ref.get('name', 'Official')} shows lenient card issuance history.")
            confidence -= 8

    # 5. Odds Bracket Risk
    if odds >= 3.50:
        risks.append(f"Underdog price profile (@ {odds:.2f}) carries elevated short-term variance.")
        confidence -= 6
    elif odds <= 1.45:
        risks.append(f"Heavy favorite price (@ {odds:.2f}) limits upside with asymmetric downside exposure.")

    # Determine Verdict
    confidence = max(40, min(95, confidence))
    if confidence >= 75 and len(risks) <= 1:
        verdict = "GO"
        summary = f"High-conviction value opportunity on {selection} (@ {odds:.2f}) with solid tactical and statistical alignment."
    elif confidence >= 60 and len(risks) <= 2:
        verdict = "CAUTION"
        summary = f"Positive expected value confirmed (+{ev_pct}% EV), but risk flags suggest disciplined fractional Kelly staking."
    else:
        verdict = "NO-GO"
        summary = f"Model detects +EV, but qualitative traps and volatility outweigh theoretical margin. Advised pass."

    tactical_angle = f"Expected tempo: {match.get('most_likely_score', '1-1')}. Matchup balance relies on {home} pitch conversion against {away}'s transition defense."

    return {
        "verdict": verdict,
        "confidence_score": confidence,
        "summary": summary,
        "pros": pros if pros else ["Positive mathematical value identified by multi-league ensemble."],
        "risks": risks if risks else ["Standard football single-match variance."],
        "tactical_angle": tactical_angle,
        "source": "heuristic_auditor"
    }


_CIRCUIT_BREAKER_ACTIVE = False
_CACHE_PATH = Path(__file__).resolve().parents[3] / "data" / "cache" / "football_audits_cache.json"

def _load_cache() -> Dict[str, Any]:
    if _CACHE_PATH.exists():
        try:
            with open(_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_cache(cache: Dict[str, Any]) -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass


def audit_football_match(match: Dict[str, Any], use_llm: bool = True) -> Dict[str, Any]:
    """Audit a football match using Gemini 3.6 Flash if available, with deterministic fallback."""
    global _CIRCUIT_BREAKER_ACTIVE
    
    home = match.get("home_team", "Home")
    away = match.get("away_team", "Away")
    date_str = (match.get("date") or "")[:10]
    pick = match.get("best_pick") or {}
    selection = pick.get("selection", f"{home} Win")
    cache_key = f"{home}_{away}_{date_str}_{selection}".lower().replace(" ", "_")

    # Check cache first
    cache = _load_cache()
    if cache_key in cache:
        res = dict(cache[cache_key])
        res["cached"] = True
        return res

    api_key = get_gemini_api_key() if use_llm else None
    
    if not api_key or _CIRCUIT_BREAKER_ACTIVE:
        res = _local_heuristic_audit(match)
        cache[cache_key] = res
        _save_cache(cache)
        return res

    try:
        from google import genai
        client = genai.Client(api_key=api_key)

        league = match.get("league_name") or match.get("league")
        odds = pick.get("odds", match.get("odds_home", 2.0))
        ev = round(float(pick.get("ev", 0.0)) * 100.0, 1)

        prompt = f"""You are a veteran sports betting risk auditor. Critically audit the following football value bet recommendation.
Do NOT be agreeable or hype the bet. Focus on real risks: short rest, fixture congestion, psychological traps, team form volatility, referee style, and market pricing traps.

MATCH CONTEXT:
- Match: {home} vs {away}
- League: {league} ({date_str})
- Recommended Pick: {selection} @ {odds} (+{ev}% EV)
- Expected Scoreline: {match.get('most_likely_score', 'N/A')}
- Elo Ratings: {home} ({match.get('home_elo', '1500')}) vs {away} ({match.get('away_elo', '1500')})
- Expected Goals: Home {match.get('expected_goals_home', 1.3):.2f} xG, Away {match.get('expected_goals_away', 1.1):.2f} xG
- Referee: {match.get('referee', {}).get('name', 'Unknown')} ({match.get('referee', {}).get('strictness_label', 'Neutral')})

OUTPUT FORMAT: Return ONLY valid JSON with this exact schema (no markdown fences, no extra text):
{{
  "verdict": "GO" or "CAUTION" or "NO-GO",
  "confidence_score": 1-100,
  "summary": "1-2 sentence executive verdict",
  "pros": ["bullet 1", "bullet 2", "bullet 3"],
  "risks": ["risk 1", "risk 2"],
  "tactical_angle": "1 sentence tactical summary"
}}
"""

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
        )

        txt = response.text.strip()
        if txt.startswith("```"):
            txt = re.sub(r"^```(?:json)?\n?", "", txt)
            txt = re.sub(r"\n?```$", "", txt)
        
        parsed = json.loads(txt)
        parsed["source"] = "gemini_3.6_flash"
        cache[cache_key] = parsed
        _save_cache(cache)
        return parsed

    except Exception as e:
        logger.warning(f"Gemini audit encountered {e}; tripping circuit breaker and falling back to heuristic auditor.")
        _CIRCUIT_BREAKER_ACTIVE = True
        res = _local_heuristic_audit(match)
        res["source"] = "heuristic_auditor_fallback"
        cache[cache_key] = res
        _save_cache(cache)
        return res
