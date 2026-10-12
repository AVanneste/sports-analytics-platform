"""Pre-match team news (injuries, suspensions, doubts) from Gemini with Google Search grounding.

Information for the match cards only: it does not feed any model. Each match kicking off within
HOURS_AHEAD gets one grounded call, cached in cache/team_news.json and refreshed after MAX_AGE_HOURS;
at most DAILY_CAP calls a run (search grounding is billed per search), soonest kick-offs first.
"""
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import requests

from sports_common.jsonstore import read_json, write_json_atomic
from sports_common.secrets import get_secret, is_usable_key, redact

logger = logging.getLogger(__name__)

CACHE = Path(__file__).resolve().parent.parent / "cache" / "team_news.json"
MODEL = "gemini-flash-latest"  # Google's alias for the current Flash model (older names get retired)
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
HOURS_AHEAD = 48
MAX_AGE_HOURS = 20
DAILY_CAP = 40

PROMPTS = {
    "football": ("{home} vs {away}, {competition}, {date}. In at most 4 short bullet points, list confirmed "
                 "injuries, suspensions and doubtful players for each team, from news of the last 7 days. "
                 "Write 'No recent news found' for a team without news. No predictions, no betting advice."),
    "tennis": ("{home} vs {away}, {competition}, {date} (tennis). In at most 3 short bullet points, report any "
               "injury, illness, retirement or fitness doubt for either player from news of the last 7 days. "
               "Write 'No recent news found' if there is none. No predictions, no betting advice."),
}


def ask_gemini(prompt: str, key: str) -> Optional[Dict]:
    """{text, sources: [{title, url}]} from one grounded call, or None."""
    body = {"contents": [{"parts": [{"text": prompt}]}], "tools": [{"google_search": {}}]}
    try:
        r = requests.post(URL, params={"key": key}, json=body, timeout=120)
        r.raise_for_status()
        candidate = r.json()["candidates"][0]
    except (requests.RequestException, KeyError, IndexError, ValueError) as e:
        logger.warning(f"Team news unavailable: {redact(e)}")
        return None
    text = "".join(p.get("text", "") for p in candidate.get("content", {}).get("parts", [])).strip()
    chunks = (candidate.get("groundingMetadata") or {}).get("groundingChunks") or []
    sources = [{"title": c["web"].get("title"), "url": c["web"].get("uri")} for c in chunks if c.get("web")]
    return {"text": text, "sources": sources[:5]} if text else None


def attach_team_news(matches: List[Dict], sport: str, now: Optional[datetime] = None, cap: int = DAILY_CAP) -> int:
    """Add ``team_news`` to each match from the cache, fetching what is missing or stale for
    matches within HOURS_AHEAD (soonest first, ``cap`` calls at most). Returns the calls made."""
    now = now or datetime.now(timezone.utc)
    cache: Dict[str, Dict] = read_json(CACHE, default={}) or {}
    key = get_secret("GEMINI_API_KEY")
    calls = 0

    def kickoff(m: Dict) -> Optional[datetime]:
        raw = m.get("commence_time") or m.get("date")
        try:
            t = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return None
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)

    soon = sorted((m for m in matches if (t := kickoff(m)) and now < t <= now + timedelta(hours=HOURS_AHEAD)), key=kickoff)
    for m in soon:
        mid = str(m.get("match_id"))
        cached = cache.get(mid)
        fresh = cached and now - datetime.fromisoformat(cached["fetched_at"]) < timedelta(hours=MAX_AGE_HOURS)
        if fresh or not is_usable_key(key) or calls >= cap:
            continue
        home, away = (m.get("home_team"), m.get("away_team")) if sport == "football" else (m.get("p1_name"), m.get("p2_name"))
        prompt = PROMPTS[sport].format(home=home, away=away, date=kickoff(m).strftime("%d %B %Y"),
                                       competition=m.get("league_name") or m.get("tourney_name") or m.get("league") or "")
        calls += 1
        news = ask_gemini(prompt, key)
        if news:
            cache[mid] = {**news, "fetched_at": now.isoformat(timespec="seconds")}
    for m in matches:
        if str(m.get("match_id")) in cache:
            m["team_news"] = cache[str(m.get("match_id"))]
    # forget matches that have been played
    keep = {str(m.get("match_id")) for m in matches}
    cache = {k: v for k, v in cache.items() if k in keep or now - datetime.fromisoformat(v["fetched_at"]) < timedelta(days=3)}
    write_json_atomic(CACHE, cache)
    if calls:
        logger.info(f"Team news: {calls} Gemini calls for {sport} ({len(soon)} matches within {HOURS_AHEAD}h)")
    return calls
