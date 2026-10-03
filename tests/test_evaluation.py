"""Model-vs-market evaluation maths and ledger reports."""
import math

import numpy as np
import pytest

from sports_common.evaluation import (
    brier, compare_to_market, devig, evaluate_football_ledger, evaluate_tennis_ledger,
    fit_market_blend_weight, log_loss, reliability_table, summarize_bets, verdict,
)


def test_devig_removes_margin_and_rejects_bad_prices():
    probs = devig([1.91, 1.91])
    assert probs == pytest.approx([0.5, 0.5])
    assert devig([2.0, 3.4, 3.8]).sum() == pytest.approx(1.0)
    for bad in ([1.0, 2.0], [None, 2.0], [float("nan"), 2.0], [], ["x", 2.0]):
        assert devig(bad) is None


def test_log_loss_and_brier_match_hand_calculation():
    probs = np.array([[0.5, 0.3, 0.2], [0.2, 0.2, 0.6]])
    y = np.array([0, 2])
    assert log_loss(probs, y) == pytest.approx(-(math.log(0.5) + math.log(0.6)) / 2)
    assert brier(probs, y) == pytest.approx(((0.25 + 0.09 + 0.04) + (0.04 + 0.04 + 0.16)) / 2)
    assert log_loss(np.array([0.8, 0.3]), np.array([1, 0])) == pytest.approx(-(math.log(0.8) + math.log(0.7)) / 2)


def test_compare_to_market_sign_convention():
    y = np.array([0, 0, 0, 1])
    sharp = np.array([0.9, 0.9, 0.9, 0.1])     # P(class 1) as binary probabilities
    vague = np.array([0.5, 0.5, 0.5, 0.5])
    res = compare_to_market(1 - sharp, 1 - vague, y)
    assert res["log_loss_skill"] < 0  # model (sharp) beats market (vague)
    assert "beat the market" in verdict(dict(res, n=100))
    assert "trails" in verdict(compare_to_market(1 - vague, 1 - sharp, y) | {"n": 100})
    assert "not enough" in verdict(res)


def test_blend_weight_prefers_the_better_source():
    rng = np.random.default_rng(0)
    truth = rng.uniform(0.2, 0.8, 4000)
    y = (rng.uniform(size=4000) < truth).astype(int)
    market = truth                               # perfectly informed
    model = np.clip(truth + rng.normal(0, 0.25, 4000), 0.01, 0.99)  # noisy
    fit = fit_market_blend_weight(model, market, y)
    assert fit["weight"] <= 0.2


def test_reliability_table_buckets():
    rows = reliability_table([0.05, 0.15, 0.95, 1.0], [0, 1, 1, 1], bins=10)
    assert rows[0]["bucket"] == "0.0-0.1" and rows[-1]["n"] == 2


def test_summarize_bets_reports_claimed_vs_actual():
    s = summarize_bets([100, 100], [172.0, -100.0], [0.33, 0.10])
    assert s["roi_pct"] == 36.0 and s["claimed_ev_pct"] == 21.5 and s["expected_pnl_if_claims_true"] == 43.0


def _fb_record(**kw):
    rec = {"status": "settled", "actual_score": "0-2", "league": "EPL",
           "prob_home": 0.3, "prob_draw": 0.2, "prob_away": 0.5,
           "odds_home": 2.58, "odds_draw": 3.4, "odds_away": 2.72,
           "best_pick": {"market": "1X2", "selection": "Away Win", "odds": 2.72, "ev": 0.33, "kelly": 0.049},
           "won": True, "stake": 100.0, "flat_pnl": 172.0, "kelly_stake": 49.0, "kelly_pnl": 84.28}
    rec.update(kw)
    return rec


def test_football_ledger_report_and_clv():
    records = [
        _fb_record(),
        _fb_record(actual_score="1-1", won=False, flat_pnl=-100.0, kelly_pnl=-49.0, league="UCL",
                   first_pick={"selection": "Away Win", "odds": 3.0, "logged_at": "2026-01-01T00:00:00+00:00"},
                   odds_captured_at="2026-01-02T00:00:00+00:00"),
        {"status": "pending", "home_team": "A", "away_team": "B"},
    ]
    rep = evaluate_football_ledger(records, competition_type=lambda r: "cup" if r["league"] == "UCL" else "domestic")
    assert rep["settled"] == 2 and rep["pending"] == 1
    assert rep["match_odds_1x2"]["n"] == 2
    assert rep["bets"]["n"] == 2 and rep["bets"]["pnl"] == 72.0 and rep["bets"]["kelly"]["pnl"] == pytest.approx(35.28)
    assert set(rep["bets_by_competition"]) == {"cup", "domestic"}
    clv = rep["clv"]["price"]
    assert clv["n"] == 1 and clv["mean_pct"] == pytest.approx(100 * (3.0 / 2.72 - 1), abs=0.01)


def test_football_ledger_kelly_falls_back_for_legacy_records():
    legacy = _fb_record(won=False, flat_pnl=-100.0)
    legacy.pop("kelly_stake"); legacy.pop("kelly_pnl")
    rep = evaluate_football_ledger([legacy])
    assert rep["bets"]["kelly"]["staked"] == 49.0 and rep["bets"]["kelly"]["pnl"] == -49.0


def test_tennis_ledger_report_uses_percent_probabilities():
    records = [
        {"status": "WON", "actual_winner": "A", "p1_name": "A", "p2_name": "B", "p1_prob": 60.6, "p2_prob": 39.4,
         "p1_odds": 2.26, "p2_odds": 1.81, "best_ev": 5.1, "best_stake": 10.15, "pnl": 12.79, "flat_pnl": 25.2},
        {"status": "NO_BET", "actual_winner": "B", "p1_name": "A", "p2_name": "B", "p1_prob": 55.0, "p2_prob": 45.0,
         "p1_odds": 1.5, "p2_odds": 2.6},
        {"status": "PENDING", "p1_name": "C", "p2_name": "D"},
    ]
    rep = evaluate_tennis_ledger(records)
    assert rep["graded"] == 2 and rep["pending"] == 1
    assert rep["match_winner"]["n"] == 2
    assert rep["bets"]["n"] == 1 and rep["bets"]["roi_pct"] == pytest.approx(126.0, abs=0.1)


def test_football_holdout_market_report_scores_deployed_blend():
    import pandas as pd
    from football_core.models.train import holdout_market_report, market_probabilities

    y = pd.DataFrame({"target_1x2": [0, 2, 1], "target_over25": [1, 0, 1],
                      "odds_home": [1.8, 2.5, None], "odds_draw": [3.6, 3.3, 3.2], "odds_away": [4.5, 2.9, 2.4],
                      "odds_over25": [1.9, 2.0, 1.8], "odds_under25": [1.9, 1.8, 2.0]})
    X = pd.DataFrame({"dc_prob_home": [0.5, 0.3, 0.4], "dc_prob_draw": [0.3, 0.3, 0.3],
                      "dc_prob_away": [0.2, 0.4, 0.3], "dc_prob_over25": [0.55, 0.45, 0.5]})
    probs, mask = market_probabilities(y, ["odds_home", "odds_draw", "odds_away"])
    assert mask.tolist() == [True, True, False] and probs[0].sum() == pytest.approx(1.0)
    rep = holdout_market_report(X, y, np.array([[0.5, 0.3, 0.2]] * 3), np.array([0.5, 0.5, 0.5]))
    assert rep["holdout_vs_market_1x2"]["n"] == 2 and rep["holdout_vs_market_over25"]["n"] == 3


def test_tennis_holdout_market_report_skips_unpriced_rows():
    import pandas as pd
    from tennis_core.models.train import holdout_market_report

    X = pd.DataFrame({"p1_odds": [1.5, 2.6, None], "p2_odds": [2.6, 1.5, 1.9]})
    rep = holdout_market_report(X, pd.Series([1, 0, 1]), np.array([0.6, 0.4, 0.5]))
    assert rep["holdout_vs_market"]["n"] == 2
    assert holdout_market_report(pd.DataFrame({"x": [1]}), pd.Series([1]), np.array([0.5])) == {}
