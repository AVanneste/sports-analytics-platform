"""Market-aware picks: shrinkage toward the market, EV credibility cap, low-confidence exclusions."""
import numpy as np
import pytest

from sports_common.betting import (
    MAX_CREDIBLE_EV, backtest_value_bets, blend_with_market, devig, expected_value, kelly_fraction,
)
from synthetic import make_football_matches


def test_blend_with_market_shrinks_toward_vig_free_price():
    final, market = blend_with_market((0.5, 0.2, 0.3), (2.6, 3.4, 2.7), model_weight=0.3)
    assert market == pytest.approx(list(devig([2.6, 3.4, 2.7])))
    assert sum(final) == pytest.approx(1.0)
    for f, model, mkt in zip(final, (0.5, 0.2, 0.3), market):
        assert min(model, mkt) - 1e-9 <= f <= max(model, mkt) + 1e-9
    assert blend_with_market((0.5, 0.5), (None, 1.9), 0.3) == ([0.5, 0.5], None)
    assert blend_with_market((0.7, 0.3), (1.5, 2.8), 0.0)[0] == pytest.approx(list(devig([1.5, 2.8])))


def test_ev_and_kelly_basics():
    assert expected_value(0.5, 2.2) == pytest.approx(0.1)
    assert kelly_fraction(0.5, 2.2) == pytest.approx(0.25 * (1.2 * 0.5 - 0.5) / 1.2)
    assert kelly_fraction(0.4, 2.0) == 0.0
    assert kelly_fraction(0.9, 2.0, cap=0.05) == 0.05


def test_backtest_picks_best_qualifying_selection_and_respects_cap():
    probs = np.array([[0.60, 0.40], [0.80, 0.20], [0.50, 0.50]])
    odds = np.array([[1.90, 2.00], [1.50, 6.00], [1.80, 2.10]])
    outcomes = np.array([0, 0, 1])
    res = backtest_value_bets(probs, odds, outcomes, min_ev=0.03)
    # row 0: home EV +14% -> win (+0.9); row 1: home EV +20% -> win (+0.5); row 2: away EV +5% -> win (+1.1)
    assert res["bets"] == 3 and res["wins"] == 3 and res["roi_pct"] == pytest.approx(83.3, abs=0.1)
    capped = backtest_value_bets(probs, odds, outcomes, min_ev=0.03, max_ev=MAX_CREDIBLE_EV)
    assert capped["bets"] == 2  # the +20% "edge" is treated as a model error


def test_tennis_value_analysis_refuses_implausible_edges():
    from tennis_core.betting.value import analyze_betting_value
    plausible = analyze_betting_value("A", "B", 0.55, 0.45, p1_odds=1.95, p2_odds=1.95)
    assert plausible["recommended_pick"] == "A" and plausible["has_value"] and not plausible["ev_suspect"]
    implausible = analyze_betting_value("A", "B", 0.70, 0.30, p1_odds=2.10, p2_odds=1.80)  # EV +47%
    assert implausible["recommended_pick"] is None and implausible["has_value"] is False
    assert implausible["ev_suspect"] is True


@pytest.fixture(scope="module")
def predictor():
    from football_core.features.builder import FootballFeaturePipeline
    from football_core.models.predictor import FootballPredictor
    from football_core.models.train import train_league_models
    pipe = FootballFeaturePipeline("EPL")
    X, y = pipe.process_historical_matches(make_football_matches(seasons=4))
    models, metrics = train_league_models(X, y, league_key="EPL")
    pred = FootballPredictor.__new__(FootballPredictor)
    pred.bundles = {"EPL": {"league_key": "EPL", "pipeline": pipe, "models": models, "metrics": metrics}}
    pred._settled_cache = None
    return pred, metrics


def test_training_records_market_weights_and_backtests(predictor):
    _, metrics = predictor
    assert set(metrics["market_weights"]) == {"1x2", "over25", "btts"}
    assert all(0.0 <= w <= 1.0 for w in metrics["market_weights"].values())
    for key in ("backtest_1x2_model_only", "backtest_1x2_market_aware", "holdout_final_vs_market_1x2"):
        assert key in metrics


def test_domestic_prediction_is_shrunk_toward_market(predictor):
    pred, metrics = predictor
    res = pred.predict_match("EPL", "Team00", "Team09", match_date="2026-10-04",
                             odds_home=3.0, odds_draw=3.4, odds_away=2.4)
    assert res["market_weights"]["1x2"] == metrics["market_weights"]["1x2"]
    for side in ("home", "draw", "away"):
        model, market, final = res[f"model_prob_{side}"], res[f"market_prob_{side}"], res[f"prob_{side}"]
        assert min(model, market) - 1e-9 <= final <= max(model, market) + 1e-9
    assert res["low_confidence"] is False


def test_absurd_prices_are_flagged_and_never_recommended(predictor):
    pred, _ = predictor
    res = pred.predict_match("EPL", "Team00", "Team09", match_date="2026-10-04",
                             odds_home=9.0, odds_draw=9.0, odds_away=1.15)
    home = next(i for i in res["betting_insights"] if i["selection"] == "Home Win")
    assert home["ev"] > MAX_CREDIBLE_EV and home["ev_suspect"] is True
    assert res["best_pick"]["selection"] != "Home Win" or res["has_value"] is False


def test_cross_pool_cup_ties_are_low_confidence_and_never_value(predictor):
    pred, _ = predictor
    res = pred.predict_match("UCL", "Team00", "Galatasaray", match_date="2026-10-21",
                             odds_home=1.5, odds_draw=4.5, odds_away=6.0)
    assert res["low_confidence"] is True and "not covered" in res["low_confidence_reason"]
    assert res["has_value"] is False


def test_competitions_never_validated_against_the_market_produce_no_value_picks(predictor):
    pred, metrics = predictor
    unvalidated = dict(pred.bundles["EPL"], metrics={k: v for k, v in metrics.items() if k != "market_weights"})
    pred.bundles["EPL_old"] = unvalidated
    try:
        from football_core.config import LEAGUES
        LEAGUES["EPL_old"] = dict(LEAGUES["EPL"])
        res = pred.predict_match("EPL_old", "Team00", "Team09", match_date="2026-10-04",
                                 odds_home=3.5, odds_draw=3.6, odds_away=2.2)
        assert res["market_validated"] is False and res["has_value"] is False
    finally:
        LEAGUES.pop("EPL_old", None)
        pred.bundles.pop("EPL_old", None)


def test_only_markets_fitted_on_real_prices_can_be_value_picks(predictor, monkeypatch):
    pred, metrics = predictor
    weights = dict(metrics["market_weights"], btts=1.0)  # trust the model fully on BTTS...
    monkeypatch.setitem(pred.bundles["EPL"], "metrics", dict(metrics, market_weights=weights))
    res = pred.predict_match("EPL", "Team00", "Team09", match_date="2026-10-04",
                             odds_btts_yes=3.0, odds_btts_no=1.25,
                             odds_corners_over95=3.0, odds_corners_under95=1.3)
    # ...yet BTTS/corners were never validated against historical prices, so no pick
    assert res["best_pick"]["market"] not in ("BTTS", "Corners") or res["has_value"] is False
