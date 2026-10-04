"""Scraped data sources: Wikidata birth dates (name matching, age lookup)."""
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
