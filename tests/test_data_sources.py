"""Scraped data sources: Wikidata birth dates and Opta Power Rankings."""
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest


# ------------------------------------------------------------------ Wikidata birth dates
def _person(label, dob, tour="atp", links=10, qid=None):
    return {"qid": qid or label, "tour": tour, "labels": {label}, "dob": dob, "links": links}


def _spans(*names, tour="atp", first="2020-01-01", last="2025-01-01"):
    return pd.DataFrame({"name": list(names), "tour": tour, "first": pd.Timestamp(first), "last": pd.Timestamp(last)})


def test_parse_tennis_data_names():
    from tennis_core.data.birthdates import parse_name
    assert parse_name("Auger-Aliassime F.") == (["auger", "aliassime"], "f", False)
    assert parse_name("Fernandez L.A.") == (["fernandez"], "la", True)
    assert parse_name("Wang Xin.") == (["wang"], "xin", False)


def test_wikidata_names_match_tennis_data_spellings():
    from tennis_core.data.birthdates import match_players
    people = [
        _person("Félix Auger-Aliassime", "2000-08-08"),
        _person("Christopher O'Connell", "1994-06-03"),
        _person("Laslo Đere", "1995-06-02"),
        _person("Julia Görges", "1988-11-02", tour="wta"),
        _person("Wang Xinyu", "2001-09-26", tour="wta"),
        _person("Wang Xiyu", "2001-03-28", tour="wta"),
        _person("Leylah Fernandez", "2002-09-06", tour="wta"),
        _person("Roberto Bautista Agut", "1988-04-14"),
    ]
    spans = pd.concat([_spans("Auger-Aliassime F.", "O Connell C.", "Djere L.", "Bautista R."),
                       _spans("Goerges J.", "Wang Xin.", "Wang Xiy.", "Fernandez L.A.", tour="wta", first="2019-01-01")])
    got = dict(zip(match_players(spans, people)["name"], match_players(spans, people)["birthdate"]))
    assert got == {"Auger-Aliassime F.": "2000-08-08", "O Connell C.": "1994-06-03", "Djere L.": "1995-06-02",
                   "Bautista R.": "1988-04-14", "Goerges J.": "1988-11-02", "Wang Xin.": "2001-09-26",
                   "Wang Xiy.": "2001-03-28", "Fernandez L.A.": "2002-09-06"}


def test_ambiguous_or_implausible_people_are_left_unmatched():
    from tennis_core.data.birthdates import match_players
    people = [_person("Marta Kostyuk", "2002-06-28", tour="wta", links=40),
              _person("Mariya Kostyuk", "1990-01-01", tour="wta", links=3),
              _person("Caroline Dolehide", "1998-09-05", tour="wta", links=10),
              _person("Courtney Dolehide", "1996-01-01", tour="wta", links=8),
              _person("Andrea Rossi", "1950-01-01")]
    table = match_players(pd.concat([_spans("Kostyuk M.", "Dolehide C.", tour="wta"), _spans("Rossi A.")]), people)
    assert dict(zip(table["name"], table["birthdate"])) == {"Kostyuk M.": "2002-06-28"}  # clear favourite only


def test_player_age_lookup(tmp_path, monkeypatch):
    from tennis_core.data import birthdates
    from tennis_core.data.player_profiles import get_player_age
    path = tmp_path / "births.csv"
    pd.DataFrame({"name": ["Sakkari M.", "Wang Xiy."], "tour": "wta", "birthdate": ["1995-07-25", "2001-03-28"],
                  "wikidata": ["Q1", "Q2"]}).to_csv(path, index=False)
    monkeypatch.setattr(birthdates, "BIRTHDATES_PATH", path)
    birthdates.load_birthdates.cache_clear()
    birthdates.birthdate_for.cache_clear()
    try:
        assert get_player_age("Sakkari M.", date(2026, 7, 24)) == 30
        assert get_player_age("Sakkari M.", date(2026, 7, 25)) == 31
        assert get_player_age("Maria Sakkari", date(2026, 10, 5)) == 31  # live feeds' full names
        assert get_player_age("Wang X.", date(2026, 10, 5)) is None  # unmatched tennis-data name: never guessed
    finally:
        birthdates.load_birthdates.cache_clear()
        birthdates.birthdate_for.cache_clear()


# ------------------------------------------------------------------ Opta Power Rankings
@pytest.fixture
def opta_table(tmp_path, monkeypatch):
    from football_core.data import opta_power as op
    payload = [
        {"contestantName": "Arsenal", "contestantShortName": "Arsenal", "contestantClubName": "Arsenal FC", "currentRating": 100.0, "rank": 1, "tmcl": "eng"},
        {"contestantName": "Arsenal", "contestantShortName": "Arsenal", "contestantClubName": "Arsenal de Sarandí", "currentRating": 70.0, "rank": 900, "tmcl": "arg"},
        {"contestantName": "Union Saint-Gilloise", "contestantShortName": "Union SG", "contestantClubName": "Royale Union Saint-Gilloise", "currentRating": 91.4, "rank": 20, "tmcl": "bel"},
        {"contestantName": "Saint-Gilloise", "contestantShortName": "Union SG II", "contestantClubName": "Union Saint-Gilloise II", "currentRating": 60.2, "rank": 4000, "tmcl": "bel2"},
        {"contestantName": "NEC Nijmegen", "contestantShortName": "NEC", "contestantClubName": "NEC", "currentRating": 77.0, "rank": 700, "tmcl": "ned"},
        {"contestantName": "Galatasaray", "contestantShortName": "Galatasaray", "contestantClubName": "Galatasaray SK", "currentRating": 86.7, "rank": 63, "tmcl": "tur"},
        {"contestantName": "Team00", "contestantShortName": "Team00", "contestantClubName": "Team00", "currentRating": 90.0, "rank": 40, "tmcl": "eng"},
    ]
    path = tmp_path / "opta.csv"
    op.parse_rankings(payload, "2026-10-02").to_csv(path, index=False)
    monkeypatch.setattr(op, "RANKINGS_PATH", path)
    for cached in (op._clubs, op.load_power_rankings, op._token_index, op.club_rating):
        cached.cache_clear()
    yield op
    for cached in (op._clubs, op.load_power_rankings, op._token_index, op.club_rating):
        cached.cache_clear()


def test_opta_lookup_handles_namesakes_spellings_and_leagues(opta_table):
    op = opta_table
    assert op.club_rating("Arsenal") == (100.0, "eng")  # the higher-rated namesake
    assert op.club_rating("Arsenal", "arg") == (70.0, "arg")
    assert op.club_rating("Royale Union Saint-Gilloise") == (91.4, "bel")
    assert op.club_rating("St. Gilloise", "bel") == (91.4, "bel")  # football-data's abbreviation
    assert op.club_rating("Nijmegen") == (77.0, "ned")  # every word of the name appears
    assert op.club_rating("Galatasaray", "eng") is None  # not in that league
    assert op.club_rating("Nowhere United") is None


def test_opta_goal_scale_is_the_within_league_slope():
    from unittest import mock
    from football_core.data import opta_power as op
    ratings = {"A": (90.0, "x"), "B": (80.0, "x"), "C": (70.0, "x"), "F": (60.0, "x"),
               "D": (85.0, "y"), "E": (75.0, "y"), "G": (65.0, "y"), "H": (95.0, "y")}
    strengths = {"L1": {"A": 0.5, "B": -0.3, "C": -1.1, "F": -1.9, "Z": 9.0},  # Z unrated: ignored
                 "L2": {"D": 1.4, "E": 0.6, "G": -0.2, "H": 2.2}}  # 0.08 log-goals per point in both
    with mock.patch.object(op, "club_rating", lambda team, league_id=None: ratings.get(team)):
        assert op.goal_scale(strengths, min_clubs=8) == pytest.approx(0.08)
        assert op.goal_scale(strengths, min_clubs=30) is None
