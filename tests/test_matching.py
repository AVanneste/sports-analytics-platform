from sports_common.matching import match_events, name_score


def test_name_score():
    assert name_score("Legia Warszawa", "Legia Warsaw") == 1.0
    assert name_score("Atletico GO", "Atletico Goianiense") == 1.0
    assert name_score("KRC Genk", "Genk") == 1.0
    assert name_score("Zheng Qinwen", "Qinwen Zheng") == 1.0
    assert name_score("Genk", "Genk U21") == 0.0  # another team
    assert name_score("Real Madrid", "Real Betis") < 0.5
    assert name_score("Man City", "Manchester United") < 0.5


def test_match_events_pairs_clear_best_and_detects_swap():
    games = [{"event_id": 1, "sport": "Soccer", "start": "2026-10-12T18:45:00Z", "home": "Union St. Gilloise", "away": "Genk"},
             {"event_id": 2, "sport": "Soccer", "start": "2026-10-12T18:45:00Z", "home": "Real Madrid", "away": "Getafe"},
             {"event_id": 3, "sport": "Tennis", "start": "2026-10-12T10:00:00Z", "home": "Qinwen Zheng", "away": "Iga Swiatek"}]
    events = [{"book": "napoleon", "event_id": "a", "sport": "Soccer", "start": "2026-10-12T18:45:00Z", "home": "Royale Union Saint-Gilloise", "away": "KRC Genk"},
              {"book": "unibet", "event_id": "b", "sport": "Tennis", "start": "2026-10-12T14:20:00Z", "home": "Iga Swiatek", "away": "Zheng Qinwen"},
              {"book": "unibet", "event_id": "c", "sport": "Soccer", "start": "2026-10-12T18:45:00Z", "home": "Real Betis", "away": "Sevilla"},
              {"book": "unibet", "event_id": "d", "sport": "Soccer", "start": "2026-10-13T18:45:00Z", "home": "Genk", "away": "Union SG"}]  # next day
    assert match_events(events, games) == {("napoleon", "a"): (1, False), ("unibet", "b"): (3, True)}
