"""Ledger safety: crash-safe persistence, immutability, odds snapshots and PnL settlement."""
import json
from unittest.mock import patch

import pandas as pd
import pytest

from sports_common import jsonstore
from sports_common.jsonstore import LedgerCorruptError, daily_backup, read_json, write_json_atomic

FUTURE = "2099-06-01"
PAST = "2000-01-01"


# ---------------------------------------------------------------- jsonstore
def test_atomic_write_leaves_original_intact_when_serialisation_fails(tmp_path):
    target = tmp_path / "ledger.json"
    write_json_atomic(target, [{"a": 1}])
    with pytest.raises(TypeError):
        write_json_atomic(target, [{"bad": object()}])
    assert json.loads(target.read_text()) == [{"a": 1}]
    assert [p.name for p in tmp_path.iterdir()] == ["ledger.json"]  # no stray temp files


def test_read_json_missing_returns_default_but_corrupt_raises(tmp_path):
    assert read_json(tmp_path / "nope.json", default=[]) == []
    bad = tmp_path / "bad.json"
    bad.write_text('[{"truncated": ')
    with pytest.raises(LedgerCorruptError):
        read_json(bad, default=[])
    with pytest.raises(LedgerCorruptError):
        read_json(tmp_path / "bad.json", default=[], validate=lambda d: isinstance(d, list))


def test_daily_backup_one_copy_per_day_and_pruning(tmp_path):
    target = tmp_path / "ledger.json"
    target.write_text("[]")
    backups = tmp_path / "backups"
    for day in ("2026-01-01", "2026-01-02", "2026-01-03"):
        (backups).mkdir(exist_ok=True)
        (backups / f"ledger.{day}.json").write_text("[]")
    first = daily_backup(target, keep=2)
    again = daily_backup(target, keep=2)
    assert first == again and first.exists()
    assert len(list(backups.glob("ledger.*.json"))) == 2


# ---------------------------------------------------------------- football tracker
def _fb_tracker(tmp_path, records=None):
    from football_core.betting.tracker import PredictionTracker
    path = tmp_path / "predictions_tracker.json"
    if records is not None:
        path.write_text(json.dumps(records))
    return PredictionTracker(storage_file=path)


def _fb_pred(**overrides):
    item = {
        "match_id": "m1", "league_key": "EPL", "league": "Premier League", "date": FUTURE,
        "home_team": "Leeds", "away_team": "Brentford",
        "prob_home": 0.30, "prob_draw": 0.21, "prob_away": 0.49,
        "prob_over25": 0.57, "prob_under25": 0.43, "prob_btts_yes": 0.57, "prob_btts_no": 0.43,
        "expected_goals_home": 1.36, "expected_goals_away": 2.0, "most_likely_score": "1-1",
        "odds_home": 2.58, "odds_draw": 3.4, "odds_away": 2.72, "bookmaker": "DraftKings (ESPN)",
        "has_value": True,
        "best_pick": {"market": "1X2", "selection": "Away Win", "odds": 2.72, "prob": 0.49, "ev": 0.33, "kelly": 0.049},
    }
    item.update(overrides)
    return item


def test_football_corrupt_ledger_is_never_replaced(tmp_path):
    path = tmp_path / "predictions_tracker.json"
    path.write_text("{not json")
    from football_core.betting.tracker import PredictionTracker
    with pytest.raises(LedgerCorruptError):
        PredictionTracker(storage_file=path)
    assert path.read_text() == "{not json"


def test_football_log_stores_odds_snapshot_and_argmax_pick(tmp_path):
    tracker = _fb_tracker(tmp_path)
    assert tracker.log_prediction(_fb_pred()) is True
    rec = tracker.predictions[0]
    assert rec["pred_1x2"] == "Brentford Win"
    assert rec["odds_home"] == 2.58 and rec["bookmaker"] == "DraftKings (ESPN)"
    assert rec["opening_odds"]["odds_away"] == 2.72
    assert rec["first_pick"]["selection"] == "Away Win"
    on_disk = json.loads((tmp_path / "predictions_tracker.json").read_text())
    assert on_disk[0]["odds_away"] == 2.72


def test_football_close_probabilities_are_not_forced_to_a_draw(tmp_path):
    tracker = _fb_tracker(tmp_path)
    tracker.log_prediction(_fb_pred(prob_home=0.38, prob_draw=0.27, prob_away=0.35, most_likely_score="1-1"))
    assert tracker.predictions[0]["pred_1x2"] == "Leeds Win"


def test_football_relog_updates_latest_odds_but_keeps_opening_and_first_pick(tmp_path):
    tracker = _fb_tracker(tmp_path)
    tracker.log_prediction(_fb_pred())
    tracker.log_prediction(_fb_pred(odds_away=2.40, odds_home=None, has_value=False,
                                    best_pick={"market": "1X2", "selection": "Brentford (Fav)", "odds": 2.40, "ev": 0.0, "kelly": 0.0}))
    rec = tracker.predictions[0]
    assert len(tracker.predictions) == 1
    assert rec["odds_away"] == 2.40          # latest price (closing-line proxy)
    assert rec["odds_home"] == 2.58          # missing quote does not erase the earlier one
    assert rec["opening_odds"]["odds_away"] == 2.72
    assert rec["first_pick"]["odds"] == 2.72
    assert rec["has_value"] is False


def test_football_rejects_missing_probabilities_instead_of_inventing_them(tmp_path):
    tracker = _fb_tracker(tmp_path)
    assert tracker.log_prediction(_fb_pred(prob_draw=None)) is False
    assert tracker.predictions == []


def test_football_settlement_computes_flat_and_kelly_pnl_and_is_final(tmp_path):
    tracker = _fb_tracker(tmp_path)
    tracker.log_prediction(_fb_pred())
    assert tracker.grade_single_match("m1", fthg=0, ftag=2, hc=5, ac=4, cards=3) is True
    rec = tracker.predictions[0]
    assert rec["status"] == "settled" and rec["won"] is True
    assert rec["flat_pnl"] == pytest.approx(172.0)
    assert rec["kelly_stake"] == pytest.approx(49.0)
    assert rec["kelly_pnl"] == pytest.approx(84.28)
    assert rec["actual_corners"] == 9 and rec["correct_over25"] is False

    assert tracker.grade_single_match("m1", fthg=3, ftag=0) is False  # never re-graded
    tracker.log_prediction(_fb_pred(prob_home=0.9, prob_draw=0.05, prob_away=0.05))
    assert tracker.predictions[0]["actual_score"] == "0-2"
    assert tracker.predictions[0]["prob_home"] == 0.30


def test_football_missing_corner_stats_are_not_graded_as_under(tmp_path):
    tracker = _fb_tracker(tmp_path)
    tracker.log_prediction(_fb_pred(prob_corners_over95=0.6, expected_corners=10.4))
    tracker.grade_single_match("m1", fthg=1, ftag=1)
    rec = tracker.predictions[0]
    assert rec["actual_corners"] is None
    assert rec["correct_corners_o95"] is None and rec["corner_error"] is None


def test_football_corners_bet_is_void_when_corners_unknown(tmp_path):
    tracker = _fb_tracker(tmp_path)
    tracker.log_prediction(_fb_pred(best_pick={"market": "Corners", "selection": "Over 9.5 Corners", "odds": 1.9, "ev": 0.05, "kelly": 0.01}))
    tracker.grade_single_match("m1", fthg=1, ftag=0)
    rec = tracker.predictions[0]
    assert rec["won"] is None and rec["flat_pnl"] == 0.0 and "bet_void_reason" in rec


def test_football_past_pending_predictions_are_frozen(tmp_path):
    tracker = _fb_tracker(tmp_path)
    tracker.log_prediction(_fb_pred(date=PAST))
    tracker.log_prediction(_fb_pred(date=PAST, prob_home=0.8, prob_draw=0.1, prob_away=0.1))
    assert tracker.predictions[0]["prob_home"] == 0.30


def test_football_batch_writes_once(tmp_path):
    tracker = _fb_tracker(tmp_path)
    with patch("football_core.betting.tracker.write_json_atomic", wraps=write_json_atomic) as writer:
        with tracker.batch():
            for i in range(5):
                tracker.log_prediction(_fb_pred(match_id=f"m{i}", home_team=f"H{i}", away_team=f"A{i}"))
        assert writer.call_count == 1
    assert len(json.loads((tmp_path / "predictions_tracker.json").read_text())) == 5


def test_football_upgrade_ledger_backfills_kelly_pnl_idempotently(tmp_path):
    legacy = [
        {"match_id": "a", "status": "settled", "won": False, "flat_pnl": -100.0, "kelly_pnl": 0.0,
         "best_pick": {"market": "1X2", "selection": "Away Win", "odds": 2.72, "kelly": 0.049}},
        {"match_id": "b", "status": "settled", "won": None, "flat_pnl": 0.0, "best_pick": None},
        {"match_id": "c", "status": "pending", "home_team": "X", "away_team": "Y"},
    ]
    tracker = _fb_tracker(tmp_path, legacy)
    assert tracker.upgrade_ledger() == 2
    assert tracker.predictions[0]["kelly_pnl"] == -49.0
    assert tracker.predictions[1]["kelly_pnl"] == 0.0
    assert tracker.upgrade_ledger() == 0
    assert tracker.predictions[0]["flat_pnl"] == -100.0  # results untouched


def test_football_reconcile_handles_missing_stats_without_crashing(tmp_path):
    tracker = _fb_tracker(tmp_path)
    tracker.log_prediction(_fb_pred())
    df = pd.DataFrame([{
        "Date": pd.Timestamp(FUTURE), "HomeTeam": "Leeds", "AwayTeam": "Brentford",
        "FTHG": 2, "FTAG": 1, "FTR": "H", "HC": float("nan"), "AC": 4,
        "HY": 1, "AY": 2, "HR": 0, "AR": 0,
    }])
    assert tracker.reconcile_with_completed_matches(df) == 1
    rec = tracker.predictions[0]
    assert rec["actual_corners"] is None and rec["actual_cards"] == 3
    assert rec["won"] is False and rec["kelly_pnl"] == -49.0


# ---------------------------------------------------------------- tennis tracker
def _tn_tracker(tmp_path):
    from tennis_core.betting.tracker import PredictionTracker
    return PredictionTracker(archive_path=tmp_path / "predictions_archive.json")


def _tn_pred(**overrides):
    item = {
        "match_id": "t1", "circuit": "WTA", "tourney_name": "Monterrey", "surface": "Hard",
        "date": FUTURE, "p1_name": "Cristina Bucsa", "p2_name": "Anna Bondar",
        "p1_prob": 60.6, "p2_prob": 39.4, "p1_odds": 2.26, "p2_odds": 1.81,
        "recommended_pick": "Cristina Bucsa", "best_ev": 5.1, "best_edge": 2.3,
        "best_stake": 10.15, "best_odds": 2.26,
        "sets_games": {"expected_total_games": 24.0, "main_games_line": {"line": 23.5}, "prob_deciding_set": 49.0},
    }
    item.update(overrides)
    return item


def test_tennis_bet_settles_with_kelly_and_flat_pnl_and_is_final(tmp_path):
    tracker = _tn_tracker(tmp_path)
    tracker.log_prediction(_tn_pred())
    rec = tracker.grade_match("t1", actual_winner="Cristina Bucsa", score="6-4 3-6 6-2",
                              total_games=27, w_sets=2, l_sets=1, deciding_set=True)
    assert rec["status"] == "WON" and rec["pnl"] == pytest.approx(12.79) and rec["flat_pnl"] == pytest.approx(25.2)
    assert rec["correct_games_ou"] is True and rec["correct_deciding_set"] is False
    again = tracker.grade_match("t1", actual_winner="Anna Bondar")
    assert again["status"] == "WON" and again["actual_winner"] == "Cristina Bucsa"


def test_tennis_no_stake_means_no_bet_even_with_a_pick(tmp_path):
    tracker = _tn_tracker(tmp_path)
    tracker.log_prediction(_tn_pred(best_stake=0.0, best_ev=0.0))
    rec = tracker.grade_match("t1", actual_winner="Cristina Bucsa")
    assert rec["status"] == "NO_BET" and rec["pnl"] == 0.0 and rec["is_value_bet"] is False


def test_tennis_graded_records_are_not_overwritten_by_relogging(tmp_path):
    tracker = _tn_tracker(tmp_path)
    tracker.log_prediction(_tn_pred())
    tracker.grade_match("t1", actual_winner="Anna Bondar")
    tracker.log_prediction(_tn_pred(p1_prob=90.0, best_odds=9.0))
    rec = tracker.predictions[0]
    assert rec["status"] == "LOST" and rec["p1_prob"] == 60.6 and rec["best_odds"] == 2.26


def test_tennis_relog_keeps_opening_odds_and_first_pick(tmp_path):
    tracker = _tn_tracker(tmp_path)
    tracker.log_prediction(_tn_pred())
    tracker.log_prediction(_tn_pred(p1_odds=2.05, best_odds=2.05))
    rec = tracker.predictions[0]
    assert rec["p1_odds"] == 2.05 and rec["opening_p1_odds"] == 2.26 and rec["first_pick"]["odds"] == 2.26


def test_tennis_corrupt_archive_raises(tmp_path):
    (tmp_path / "predictions_archive.json").write_text("[")
    with pytest.raises(LedgerCorruptError):
        _tn_tracker(tmp_path)


def test_espn_score_is_written_from_winner_perspective():
    from tennis_core.data.espn_tennis import _parse_espn_competition_score
    comp = {"competitors": [
        {"winner": False, "linescores": [{"value": 6}, {"value": 3}, {"value": 4}]},
        {"winner": True, "linescores": [{"value": 4}, {"value": 6}, {"value": 6}]},
    ]}
    score, games, w_sets, l_sets, decider = _parse_espn_competition_score(comp)
    assert score == "4-6 6-3 6-4" and games == 29 and (w_sets, l_sets) == (2, 1) and decider is True


def test_espn_reconcile_ignores_a_previous_meeting_and_grades_the_right_one(tmp_path):
    from tennis_core.data import espn_tennis
    tracker = _tn_tracker(tmp_path)
    today = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d")
    old = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
    tracker.log_prediction(_tn_pred(match_id="today", date=today))
    previous_meeting = {"p1_name": "Anna Bondar", "p2_name": "Cristina Bucsa", "winner": "Anna Bondar",
                        "score": "6-1 6-1", "date": old, "total_games": 14, "w_sets": 2, "l_sets": 0, "deciding_set": False}
    with patch.object(espn_tennis, "fetch_espn_recent_completed_matches", side_effect=[[previous_meeting], []]):
        res = espn_tennis.reconcile_tennis_tracker_with_espn(tracker)
    assert res["reconciled"] == 0 and tracker.predictions[0]["status"] == "PENDING"

    same_day = dict(previous_meeting, date=today, winner="Cristina Bucsa", score="6-4 6-4", total_games=20)
    with patch.object(espn_tennis, "fetch_espn_recent_completed_matches", side_effect=[[same_day], []]):
        res = espn_tennis.reconcile_tennis_tracker_with_espn(tracker)
    assert res["reconciled"] == 1
    assert tracker.predictions[0]["status"] == "WON" and tracker.predictions[0]["score"] == "6-4 6-4"


# ---------------------------------------------------------------- downloads
def test_season_downloader_rejects_html_and_cups(tmp_path, monkeypatch):
    from football_core.data import fetcher

    class Resp:
        status_code = 200
        content = b"<!DOCTYPE html><html>parking page</html>" * 20

    monkeypatch.setattr(fetcher, "RAW_DATA_DIR", tmp_path)
    monkeypatch.setattr(fetcher.requests, "get", lambda *a, **k: Resp())
    monkeypatch.setattr(fetcher.subprocess if hasattr(fetcher, "subprocess") else __import__("subprocess"),
                        "run", lambda *a, **k: type("R", (), {"returncode": 0, "stdout": Resp.content})())
    assert fetcher.download_league_season("WorldCup", "2425") is None
    assert fetcher.download_league_season("EPL", "9999", force=True) is None
    assert not (tmp_path / "EPL" / "EPL_9999.csv").exists()
    assert fetcher._looks_like_results_csv(b"Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG\nE0,...")


def test_tennis_data_links_are_read_from_the_data_page():
    """tennis-data.co.uk moved its spreadsheets under an obscured directory in 2025."""
    from tennis_core.data.fetcher import parse_file_links
    html = ('<a href="hrjk-85HytOjkhth76j_ygh4jf7/2026/2026.xlsx">2026</a>'
            '<a href=hrjk-85HytOjkhth76j_ygh4jf7/2026w/2026.xlsx>2026 WTA</a>'
            '<a href="2012/2012.xls">old xls</a><a href="data.php">x</a>')
    links = parse_file_links(html, "https://tennis-data.co.uk/data.php")
    assert links == {("atp", 2026): "https://tennis-data.co.uk/hrjk-85HytOjkhth76j_ygh4jf7/2026/2026.xlsx",
                     ("wta", 2026): "https://tennis-data.co.uk/hrjk-85HytOjkhth76j_ygh4jf7/2026w/2026.xlsx"}

