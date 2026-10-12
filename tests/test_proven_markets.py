from football_core.models.predictor import proven_markets


def test_only_markets_with_a_profitable_holdout_are_proven():
    metrics = {"backtest_1x2_market_aware": {"bets": 72, "roi_pct": 4.0},
               "backtest_over25_market_aware": {"bets": 35, "roi_pct": -1.1},
               "backtest_btts_market_aware": {"bets": 12, "roi_pct": 20.0}}
    assert proven_markets(metrics) == {"1X2"}
    assert proven_markets({}) == set()
