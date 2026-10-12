from datetime import datetime, timezone

from sports_common import team_news


def test_cache_cap_and_window(tmp_path, monkeypatch):
    monkeypatch.setattr(team_news, "CACHE", tmp_path / "news.json")
    monkeypatch.setattr(team_news, "get_secret", lambda name: "real-key-123")
    calls = []
    monkeypatch.setattr(team_news, "ask_gemini", lambda prompt, key: calls.append(prompt) or {"text": "- X injured", "sources": []})
    now = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
    m = lambda i, day: {"match_id": f"m{i}", "home_team": f"H{i}", "away_team": f"A{i}", "date": f"2026-10-{day}T18:00:00Z"}
    matches = [m(1, 24), m(2, 25), m(3, 25), m(4, 30)]  # m4 is outside the 48h window
    assert team_news.attach_team_news(matches, "football", now=now, cap=2) == 2
    assert [x.get("team_news", {}).get("text") for x in matches] == ["- X injured", "- X injured", None, None]
    again = [m(1, 24), m(2, 25), m(3, 25)]
    assert team_news.attach_team_news(again, "football", now=now, cap=2) == 1  # m1, m2 cached; m3 fetched
    assert all(x.get("team_news") for x in again) and len(calls) == 3
