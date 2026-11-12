import pandas as pd

from football_core.utils import team_resolver as tr

KNOWN = {"Genk", "Standard", "Birmingham", "Istanbulspor", "Buyuksehyr", "Sociedad", "Sociedad B", "Ayr", "Inverness C"}


def test_resolve_exact_table_alias_and_unique_whole_word_match():
    assert tr.resolve("Genk", KNOWN) == "Genk"
    assert tr.resolve("Birmingham City", KNOWN) == "Birmingham"                      # unique whole-word match
    assert tr.resolve("Racing Genk", KNOWN, table={"racing genk": "Genk"}) == "Genk"  # hand-kept table
    assert tr.resolve("Inverness Caledonian Thistle", KNOWN, aliases={"inverness caledonian thistle": "Inverness C"}) == "Inverness C"
    assert tr.resolve("Inverness Caledonian Thistle", KNOWN) is None                  # nothing shares a word
    assert tr.resolve("Istanbul Basaksehir", KNOWN) is None                           # a shared prefix is not a match
    assert tr.resolve("Real Sociedad II", KNOWN) is None                              # a reserve side is another club
    assert tr.resolve("Real Sociedad", KNOWN) == "Sociedad"
    assert tr.resolve("", KNOWN) is None


def test_learn_aliases_from_same_day_same_score_matches():
    results = pd.DataFrame({"Date": pd.to_datetime(["2026-11-01", "2026-11-08", "2026-11-08"]),
                            "HomeTeam": ["Genk", "Standard", "Birmingham"], "AwayTeam": ["Standard", "Genk", "Ayr"],
                            "FTHG": [2, 0, 1], "FTAG": [1, 0, 1]})
    ledger = [{"date": "2026-11-01", "home_team": "Racing Genk", "away_team": "Standard Liege", "actual_score": "2-1"},
              {"date": "2026-11-08", "home_team": "Standard Liege", "away_team": "Racing Genk", "actual_score": "0-0"},
              {"date": "2026-11-08", "home_team": "Birmingham City", "away_team": "Ayr United", "actual_score": "1-1"}]
    got = tr.learn_aliases(tr.ledger_pairs(ledger, results), KNOWN)
    assert got["racing genk"] == "Genk" and got["standard liege"] == "Standard"      # two pairings each
    assert "birmingham city" not in got                                               # one pairing is not enough


def test_update_aliases_writes_the_cache_and_reports_unresolved(tmp_path):
    path = tmp_path / "aliases.json"
    report = tr.update_aliases({"Belgium": KNOWN}, {"Belgium": ["Racing Genk", "Zzz United"]}, {}, {},
                               table={"racing genk": "Genk"}, path=path, ask_ai=False)
    assert report["Belgium"] == {"teams": 2, "unresolved": ["Zzz United"]}
    assert tr.load_aliases(path) == {"Belgium": {}}


def test_gemini_answers_are_kept_only_when_they_are_known_names(monkeypatch):
    class Reply:
        def raise_for_status(self): pass
        def json(self): return {"candidates": [{"content": {"parts": [{"text": '{"A Town": "Genk", "B Town": "Invented FC", "C Town": null}'}]}}]}
    monkeypatch.setattr(tr.requests, "post", lambda *a, **k: Reply())
    assert tr.ask_gemini("Belgium", ["A Town", "B Town", "C Town"], sorted(KNOWN), "key") == {"a town": "Genk"}
