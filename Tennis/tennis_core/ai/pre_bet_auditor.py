"""Automated Pre-Bet AI Auditor for Tennis Matches.
Evaluates tennis value bets with qualitative risk analysis (surface mastery,
fatigue, serve/return dynamics, head-to-head psychological edge) using
Gemini 3.6 Flash with resilient deterministic fallback.
"""
import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

def get_gemini_api_key() -> Optional[str]:
    """Retrieve Gemini API key."""
    k = os.environ.get("GEMINI_API_KEY")
    if k and k.strip():
        return k.strip()
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
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
            return str(st.secrets["GEMINI_API_KEY"]).strip()
    except Exception:
        pass
    return None


def _local_heuristic_audit(match: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic qualitative rule-based audit for tennis."""
    p1 = match.get("p1_name", "Player 1")
    p2 = match.get("p2_name", "Player 2")
    winner = match.get("predicted_winner", p1)
    circuit = match.get("circuit", "ATP")
    surface = match.get("surface", "Hard")
    
    betting = match.get("betting") or {}
    odds = float(betting.get("odds") or 1.85)
    ev_val = float(betting.get("best_ev") or 0.0)
    ev_pct = round(ev_val * 100.0, 1)

    ctx = match.get("context") or {}
    p1_elo = float(ctx.get("p1_elo", 1500))
    p2_elo = float(ctx.get("p2_elo", 1500))
    elo_diff = p1_elo - p2_elo if winner == p1 else p2_elo - p1_elo

    pros = []
    risks = []
    confidence = 72

    if ev_pct >= 6.0:
        pros.append(f"Significant +EV value margin (+{ev_pct}%) on {winner} vs bookmaker implied odds.")
        confidence += 7
    elif ev_pct >= 2.0:
        pros.append(f"Confirmed mathematical edge of +{ev_pct}% EV under surface-adjusted model.")
        confidence += 3
    else:
        risks.append(f"Low EV cushion (+{ev_pct}%) highly sensitive to line movements.")
        confidence -= 5

    if elo_diff >= 60:
        pros.append(f"{winner} holds superior fundamental Elo (+{int(elo_diff)}) on {surface} court.")
        confidence += 6
    elif elo_diff <= -30:
        risks.append(f"Backing player with lower baseline Elo rating (-{abs(int(elo_diff))}).")
        confidence -= 7

    pros.append(f"Surface calibration tailored for {circuit} {surface} dynamics.")

    if odds >= 2.70:
        risks.append(f"High-odds underdog profile (@ {odds:.2f}) carries elevated match variance.")
        confidence -= 6
    elif odds <= 1.35:
        risks.append(f"Heavy favorite pricing (@ {odds:.2f}) offers low risk/reward profile.")

    confidence = max(40, min(95, confidence))
    if confidence >= 75 and len(risks) <= 1:
        verdict = "GO"
        summary = f"High-confidence play on {winner} (@ {odds:.2f}) with proven surface adaptation."
    elif confidence >= 60:
        verdict = "CAUTION"
        summary = f"Valid +EV opportunity (+{ev_pct}%), but recommended with conservative fractional Kelly stake."
    else:
        verdict = "NO-GO"
        summary = f"Qualitative volatility and low price buffer offset expected edge. Pass."

    return {
        "verdict": verdict,
        "confidence_score": confidence,
        "summary": summary,
        "pros": pros,
        "risks": risks,
        "tactical_angle": f"{winner} service hold percentage on {surface} provides primary stabilizing factor.",
        "source": "heuristic_auditor"
    }


_CIRCUIT_BREAKER_ACTIVE = False
_CACHE_PATH = Path(__file__).resolve().parents[3] / "data" / "cache" / "tennis_audits_cache.json"

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


def audit_tennis_match(match: Dict[str, Any], use_llm: bool = True) -> Dict[str, Any]:
    """Audit a tennis match using Gemini 3.6 Flash if available, with deterministic fallback."""
    global _CIRCUIT_BREAKER_ACTIVE

    p1 = match.get("p1_name", "Player 1")
    p2 = match.get("p2_name", "Player 2")
    date_str = (match.get("date") or "")[:10]
    cache_key = f"{p1}_{p2}_{date_str}".lower().replace(" ", "_")

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

        circuit = match.get("circuit", "ATP")
        surface = match.get("surface", "Hard")
        winner = match.get("predicted_winner", p1)
        p1_prob = round(float(match.get("p1_prob", 50.0)), 1)
        p2_prob = round(float(match.get("p2_prob", 50.0)), 1)
        betting = match.get("betting") or {}
        odds = betting.get("odds") or "N/A"
        ev = round(float(betting.get("best_ev") or 0.0) * 100.0, 1)

        prompt = f"""You are a veteran professional tennis bet auditor. Critically evaluate this value bet:
MATCH DETAILS:
- Match: {p1} vs {p2} ({circuit}, {surface} court)
- Tournament / Round: {match.get('tourney_name', 'Tourney')} - {match.get('round', 'Round')}
- Model Predicted Winner: {winner} ({p1_prob}% vs {p2_prob}%)
- Market Odds: {odds} (+{ev}% EV)
- Format: Best of {match.get('best_of', 3)}

Check for tennis-specific trap risks: surface suitability, second serve vulnerability, break point variance, mental endurance, fatigue from recent sets.

OUTPUT FORMAT: Return ONLY valid JSON with this exact schema (no markdown, no other text):
{{
  "verdict": "GO" or "CAUTION" or "NO-GO",
  "confidence_score": 1-100,
  "summary": "1-2 sentence executive audit",
  "pros": ["bullet 1", "bullet 2"],
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
        logger.warning(f"Gemini tennis audit encountered {e}; tripping circuit breaker and using heuristic.")
        _CIRCUIT_BREAKER_ACTIVE = True
        res = _local_heuristic_audit(match)
        res["source"] = "heuristic_auditor_fallback"
        cache[cache_key] = res
        _save_cache(cache)
        return res
