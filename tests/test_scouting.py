import pandas as pd

from football_core import scouting


def table():
    rows = []
    for i, (team, xg, xa, minutes) in enumerate([("Lokeren", 0.8, 0.3, 900), ("Lokeren", 0.2, 0.1, 880),
                                                 ("Beveren", 0.5, 0.2, 900), ("Beveren", 0.6, 0.25, 300),
                                                 ("Sunderland", 0.5, 0.2, 900)]):
        rows.append({"player_id": i, "name": f"P{i}", "team": team, "league_id": 264 if team != "Sunderland" else 48,
                     "position": "ST", "minutes": minutes, "expected_goals_per_90": xg, "expected_assists_per_90": xa,
                     "total_scoring_att": xg * 5, "expected_goalsontarget": xg * 8})
    return pd.DataFrame(rows)


def test_score_ranks_within_position_and_adjusts_for_level(monkeypatch):
    levels = {"Lokeren": (60.0, "be2"), "Beveren": (62.0, "be2"), "Sunderland": (80.0, "en2")}
    monkeypatch.setattr(scouting, "club_rating", lambda team: levels.get(team))
    df = scouting.score(table()).set_index("player_id")
    assert 3 not in df.index  # 300 of a possible 900 minutes: not a regular
    assert df.loc[0, "role_score"] > df.loc[2, "role_score"] > df.loc[1, "role_score"]
    assert df.loc[2, "role_score"] == df.loc[4, "role_score"]  # same numbers...
    assert df.loc[4, "adj_score"] - df.loc[2, "adj_score"] == 18.0 * scouting.LEVEL_WEIGHT  # ...but 18 Opta points higher
    assert df.loc[2, "expected_goalsontarget_p90"] == 0.5 * 8 * 90 / 900


def test_similar_finds_the_closest_profile(monkeypatch):
    monkeypatch.setattr(scouting, "club_rating", lambda team: None)
    df = scouting.score(table())
    best = scouting.similar(df, 2, n=1)
    assert best["player_id"].tolist() == [4]


def test_leagues_without_minutes_are_not_scored(monkeypatch):
    monkeypatch.setattr(scouting, "club_rating", lambda team: None)
    t = table()
    t.loc[t["league_id"] == 48, "minutes"] = 0  # basic tables only
    assert 4 not in set(scouting.score(t)["player_id"])
