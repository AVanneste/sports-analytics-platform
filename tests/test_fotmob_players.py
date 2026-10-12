from football_core.data.fotmob_players import parse_profile, parse_squad, pivot_tables, position_group, stat_urls


def test_position_group_reads_the_pitch_grid():
    assert [position_group(c) for c in (11, 32, 35, 38, 51, 65, 72, 75, 83, 85, 105, None)] == \
           ["GK", "FB", "CB", "FB", "FB", "DM", "W", "CM", "W", "AM", "ST", None]


def test_pivot_tables_one_row_per_player():
    row = lambda pid, value, minutes: {"ParticiantId": pid, "ParticipantName": f"P{pid}", "TeamId": 9, "TeamName": "Lokeren",
                                       "StatValue": value, "MinutesPlayed": minutes, "MatchesPlayed": 6, "Positions": [105]}
    tables = {"expected_goals_per_90": {"TopLists": [{"StatList": [row(1, 0.6, 540), row(2, 0.3, 300)]}]},
              "total_tackle": {"TopLists": [{"StatList": [row(1, 0.4, 540)]}]}}
    df = pivot_tables(tables, 264, "2026/2027").set_index("player_id")
    assert df.loc[1, "expected_goals_per_90"] == 0.6 and df.loc[1, "total_tackle"] == 0.4
    assert df.loc[2, "total_tackle"] != df.loc[2, "total_tackle"]  # NaN: not in that table
    assert (df.loc[1, "position"], df.loc[1, "league"], df.loc[1, "minutes"]) == ("ST", "Belgium First Division B", 540)


def test_stat_urls_squad_and_profile():
    league = {"stats": {"players": [{"fetchAllUrl": "https://data.fotmob.com/stats/264/season/1/expected_goals_per_90.json"}]}}
    assert stat_urls(league) == {"expected_goals_per_90": "https://data.fotmob.com/stats/264/season/1/expected_goals_per_90.json"}
    team = {"squad": {"squad": [{"members": [{"id": 7, "age": 21, "dateOfBirth": "2005-01-15", "height": 183,
                                              "transferValue": 900000, "positionIdsDesc": "ST,LW"}]}]}}
    assert parse_squad(team) == [{"player_id": 7, "age": 21, "birth_date": "2005-01-15", "height_cm": 183,
                                  "market_value_eur": 900000, "listed_positions": "ST,LW"}]
    profile = {"id": 7, "playerInformation": [{"title": "Preferred foot", "value": {"fallback": "Left"}}],
               "contractEnd": {"utcTime": "2028-06-30T00:00:00.000Z"}}
    assert parse_profile(profile) == {"player_id": 7, "foot": "Left", "contract_end": "2028-06-30"}
