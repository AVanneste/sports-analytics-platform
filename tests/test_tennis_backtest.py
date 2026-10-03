"""Tennis walk-forward harness: no lookahead, symmetric scoring, sane metrics."""
import numpy as np
import pandas as pd
import pytest

from synthetic import make_tennis_matches
from tennis_core.models.backtest import (
    EloRatingModel, compare, first_player_view, market_predictions, score_predictions, walk_forward_fitted,
)


def _matches(n=600):
    df = make_tennis_matches(n=n)
    return df.sort_values("tourney_date", kind="mergesort").reset_index(drop=True)


def test_elo_predictions_never_use_later_results():
    matches = _matches()
    full = EloRatingModel().run(matches)
    truncated = EloRatingModel().run(matches.iloc[:400])
    assert np.allclose(full.iloc[:400].to_numpy(), truncated.to_numpy())
    assert full.iloc[0] == pytest.approx(0.5)  # two unseen players


def test_elo_learns_skill_and_beats_a_coin_flip():
    matches = _matches(1500)
    p = EloRatingModel().run(matches).iloc[500:]
    assert score_predictions(matches, p)["log_loss"] < np.log(2)
    assert score_predictions(matches, p)["accuracy"] > 0.6


class _Spy:
    kind, needs_features, refit, name = "fitted", True, "MS", "spy"

    def __init__(self):
        self.calls = []

    def fit(self, matches, X_hist, y_hist):
        assert len(X_hist) == 2 * len(matches)
        self.last_date = matches["tourney_date"].max()

    def predict_rows(self, X_rows):
        self.calls.append((self.last_date, X_rows["match_date"].min()))
        return np.where(np.arange(len(X_rows)) % 2 == 0, 0.7, 0.4)  # winner view, mirror view


def test_fitted_walk_forward_trains_only_on_the_past_and_averages_both_views():
    matches = _matches(800)
    X = pd.DataFrame({"match_date": np.repeat(matches["tourney_date"].to_numpy(), 2)})
    y = pd.Series(np.tile([1, 0], len(matches)))
    spy = _Spy()
    eval_from = matches["tourney_date"].iloc[500]
    p = walk_forward_fitted(matches, X, y, spy, eval_from, min_history=100)
    assert spy.calls and all(fit_end < window_start for fit_end, window_start in spy.calls)
    assert np.allclose(p.to_numpy(), (0.7 + 1 - 0.4) / 2)
    assert p.index.equals(matches.index[matches["tourney_date"] >= eval_from])


def test_scoring_is_independent_of_which_player_is_listed_first():
    matches = pd.DataFrame({"winner_name": ["Alpha A.", "Zulu Z."], "loser_name": ["Zulu Z.", "Alpha A."]})
    p_winner = pd.Series([0.8, 0.8])
    p, y = first_player_view(matches, p_winner.to_numpy())
    assert p.tolist() == pytest.approx([0.8, 0.2]) and y.tolist() == [1, 0]
    s = score_predictions(matches, p_winner)
    assert s["log_loss"] == pytest.approx(-np.log(0.8), abs=1e-4) and s["accuracy"] == 1.0


def test_market_yardstick_and_paired_comparison():
    matches = pd.DataFrame({"winner_name": ["A", "B", "C"], "loser_name": ["X", "Y", "Z"],
                            "pinnacle_winner_odds": [1.5, np.nan, 3.0], "pinnacle_loser_odds": [2.7, 2.0, 1.4]})
    mk = market_predictions(matches, "pinnacle_winner_odds", "pinnacle_loser_odds")
    assert mk.iloc[0] + (1 / 2.7) / (1 / 1.5 + 1 / 2.7) == pytest.approx(1.0) and np.isnan(mk.iloc[1])
    diff = compare({"good": pd.Series([0.9, 0.8, 0.7]), "ref": pd.Series([0.5, 0.5, 0.5])}, "ref")["good"]
    assert diff["mean"] < 0 and diff["n"] == 3
