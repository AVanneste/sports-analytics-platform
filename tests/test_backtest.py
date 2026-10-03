"""Walk-forward backtest harness: no lookahead, correct market maths, sane metrics."""
import numpy as np
import pandas as pd
import pytest
from scipy.stats import poisson

from football_core.models.backtest import (
    BaseRateModel, DixonColesModel, PRED_1X2, compare, market_predictions, markets_from_score_matrix,
    per_match_losses, score_predictions, season_label, walk_forward,
)
from sports_common.evaluation import ece, paired_difference, rps
from synthetic import make_football_matches


def _matches(seasons=3):
    return make_football_matches(seasons=seasons).sort_values("Date", kind="mergesort").reset_index(drop=True)


def test_markets_from_independent_poisson_matrix():
    lam, mu = 1.6, 1.1
    m = np.outer(poisson.pmf(range(12), lam), poisson.pmf(range(12), mu))
    p = markets_from_score_matrix(m)
    assert p["p_home"] + p["p_draw"] + p["p_away"] == pytest.approx(1.0)
    assert p["p_over25"] == pytest.approx(1 - poisson.cdf(2, lam + mu), abs=1e-6)
    assert p["p_btts"] == pytest.approx((1 - np.exp(-lam)) * (1 - np.exp(-mu)), abs=1e-6)
    assert p["p_over15"] > p["p_over25"] > p["p_over35"]


def test_season_labels():
    dates = pd.Series(pd.to_datetime(["2022-07-01", "2023-06-30", "2023-08-12"]))
    assert season_label(dates).tolist() == ["2223", "2223", "2324"]


class _Spy:
    name, refit, needs_features = "spy", "MS", False

    def __init__(self):
        self.calls = []

    def fit(self, history, X_hist=None, y_hist=None):
        self.last_history_date = history["Date"].max()

    def predict(self, upcoming, X_up=None):
        self.calls.append((self.last_history_date, upcoming["Date"].min()))
        return pd.DataFrame({"p_home": 0.45, "p_draw": 0.27, "p_away": 0.28}, index=upcoming.index)


def test_walk_forward_never_trains_on_the_window_it_predicts():
    matches = _matches(seasons=6)
    spy = _Spy()
    eval_from = matches["Date"].iloc[400]
    preds = walk_forward(matches, [spy], eval_from)["spy"]
    assert len(spy.calls) > 3
    assert all(hist_end < window_start for hist_end, window_start in spy.calls)
    assert preds.index.equals(matches.index[matches["Date"] >= eval_from])


def test_walk_forward_respects_minimum_history():
    matches = _matches(seasons=4)
    spy = _Spy()
    out = walk_forward(matches, [spy], matches["Date"].iloc[10], min_history=300)
    assert all((matches["Date"] < start).sum() >= 300 for _, start in spy.calls)
    assert "spy" in out


def test_dixon_coles_beats_base_rate_on_strength_driven_data():
    matches = _matches(seasons=4)
    eval_from = matches["Date"].iloc[len(matches) // 2]
    preds = walk_forward(matches, [BaseRateModel(), DixonColesModel()], eval_from)
    base = score_predictions(matches, preds["base_rate"])
    dc = score_predictions(matches, preds["dixon_coles"])
    assert dc["1x2"]["log_loss"] < base["1x2"]["log_loss"]
    assert dc["score"]["log_loss"] < base["score"]["log_loss"]
    diff = compare(matches, preds, "base_rate")["dixon_coles"]["1x2"]
    assert diff["mean"] < 0 and diff["n"] == len(preds["dixon_coles"])


def test_metrics_reward_confident_correct_predictions():
    matches = _matches(seasons=1).iloc[:50]
    y = np.where(matches["FTHG"] > matches["FTAG"], 0, np.where(matches["FTHG"] == matches["FTAG"], 1, 2))
    sharp = pd.DataFrame(np.eye(3)[y] * 0.9 + 0.1 / 3, columns=PRED_1X2, index=matches.index)
    flat = pd.DataFrame(1 / 3, columns=PRED_1X2, index=matches.index)
    s, f = score_predictions(matches, sharp)["1x2"], score_predictions(matches, flat)["1x2"]
    assert s["log_loss"] < f["log_loss"] and s["rps"] < f["rps"] and s["accuracy"] == 1.0
    assert per_match_losses(matches, sharp)["1x2"].shape == (50,)


def test_market_yardstick_devigs_and_skips_missing_prices():
    matches = _matches(seasons=1).iloc[:3].copy()
    matches.loc[matches.index[1], "odds_home"] = np.nan
    mk = market_predictions(matches, "open")
    assert mk.loc[matches.index[0], PRED_1X2].sum() == pytest.approx(1.0)
    assert mk.loc[matches.index[1], PRED_1X2].isna().all()


def test_accuracy_metric_helpers():
    assert rps(np.array([[0.2, 0.3, 0.5]]), np.array([2])) == pytest.approx(((0.2) ** 2 + (0.5) ** 2) / 2)
    assert ece([0.8] * 10, [1] * 8 + [0] * 2) == pytest.approx(0.0)
    d = paired_difference([1.0, 1.0, 1.0, 1.0], [2.0, 2.0, 2.0, 3.0])
    assert d["mean"] == pytest.approx(-1.25) and d["n"] == 4


def test_count_model_recovers_team_rates_and_shrinks_referees():
    from football_core.features.count_model import TeamCountModel
    rng = np.random.default_rng(5)
    teams = [f"T{i}" for i in range(10)]
    rate = {t: 3.5 + 0.4 * i for i, t in enumerate(teams)}  # T9 wins far more corners than T0
    rows, day = [], pd.Timestamp("2021-08-01")
    for _ in range(6):
        for h in teams:
            for a in teams:
                if h != a:
                    day += pd.Timedelta(days=1)
                    rows.append({"Date": day, "HomeTeam": h, "AwayTeam": a, "HC": rng.poisson(rate[h] * 1.1),
                                 "AC": rng.poisson(rate[a]), "Referee": "Busy Ref" if rng.uniform() < 0.5 else f"R{rng.integers(0, 40)}"})
    df = pd.DataFrame(rows)
    df.loc[df.index[:5], "Referee"] = "Rare Ref"
    model = TeamCountModel("HC", "AC", referee_col="Referee").fit(df)
    assert model.fitted and model.alpha >= 0.0
    assert model.expected("T9", "T0") > model.expected("T0", "T9")
    assert model.expected("T9", "T0") == pytest.approx(rate["T9"] * 1.1 + rate["T0"], rel=0.12)
    assert abs(model.referee_factor["Rare Ref"] - 1.0) < 0.2  # 5 matches barely move it off 1
    probs = [model.prob_over("T5", "T4", line) for line in (6.5, 8.5, 10.5, 12.5)]
    assert all(0.0 < p < 1.0 for p in probs) and probs == sorted(probs, reverse=True)
    assert model.expected("Promoted FC", "T4") > 0  # unknown teams get league-average rates


def test_stacked_outcome_model_produces_valid_probabilities():
    from football_core.features.builder import FootballFeaturePipeline
    from football_core.models.backtest import StackedOutcomeModel
    matches = _matches(seasons=4)
    X, y = FootballFeaturePipeline("EPL").process_historical_matches(matches)
    preds = walk_forward(matches, [StackedOutcomeModel()], matches["Date"].iloc[len(matches) // 2], X=X, y=y)["stacked"]
    assert np.allclose(preds[PRED_1X2].sum(axis=1), 1.0)
    assert score_predictions(matches, preds)["1x2"]["n"] == len(preds)
