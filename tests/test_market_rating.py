import numpy as np
import pandas as pd

from football_core.features.market_rating import MarketRatingEngine, closing_probs


def season(n_rounds=40, seed=0):
    """Strong, middle and weak team; the closing price always favours the stronger side."""
    rng = np.random.default_rng(seed)
    strength = {"Strong": 1.0, "Mid": 0.0, "Weak": -1.0}
    rows = []
    for r in range(n_rounds):
        for h, a in (("Strong", "Mid"), ("Mid", "Weak"), ("Weak", "Strong"), ("Mid", "Strong"), ("Weak", "Mid"), ("Strong", "Weak")):
            s = 0.3 + strength[h] - strength[a]
            ph, pa = np.exp(s / 2), np.exp(-s / 2); pd_ = 1.0
            p = np.array([ph, pd_, pa]) / (ph + pd_ + pa)
            outcome = rng.choice(3, p=p)
            rows.append({"Date": pd.Timestamp("2025-08-01") + pd.Timedelta(days=r * 7 + len(rows) % 3), "HomeTeam": h, "AwayTeam": a,
                         "FTHG": [2, 1, 0][outcome], "FTAG": [0, 1, 2][outcome],
                         "B365H": round(1 / (p[0] * 1.05), 2), "B365D": round(1 / (p[1] * 1.05), 2), "B365A": round(1 / (p[2] * 1.05), 2)})
    return pd.DataFrame(rows)


def test_closing_probs_prefers_pinnacle_then_average_then_bet365():
    df = pd.DataFrame({"PSCH": [2.0, None], "PSCD": [3.5, None], "PSCA": [4.0, None], "AvgCH": [9.0, 2.5], "AvgCD": [9.0, 3.2], "AvgCA": [9.0, 3.0]})
    p = closing_probs(df, [("PSCH", "PSCD", "PSCA"), ("AvgCH", "AvgCD", "AvgCA")], 3)
    assert abs(p[0].sum() - 1) < 1e-9 and p[0, 0] > 0.45          # Pinnacle's prices, not the 9.0s
    assert p[1, 0] < 0.4 and abs(p[1].sum() - 1) < 1e-9           # no Pinnacle: the market average
    assert np.isnan(closing_probs(df.iloc[[1]].assign(AvgCH=None), [("PSCH", "PSCD", "PSCA"), ("AvgCH", "AvgCD", "AvgCA")], 3)).all()


def test_ratings_follow_the_market_and_predictions_order_the_teams():
    engine = MarketRatingEngine().fit(season())
    r = engine.rating
    assert r["Strong"] > r["Mid"] > r["Weak"]
    strong_home = engine.predict("Strong", "Weak"); weak_home = engine.predict("Weak", "Strong")
    assert strong_home["p_home"] > 0.6 > weak_home["p_home"] and abs(sum(strong_home[k] for k in ("p_home", "p_draw", "p_away")) - 1) < 1e-9
    assert engine.predict("Strong", "Unknown")["seen"] == 0       # an unseen team is flagged thin
    assert MarketRatingEngine().predict("A", "B") is None          # not fitted yet


def test_a_matchs_own_price_cannot_leak_into_its_prediction():
    history = season(60)
    engine = MarketRatingEngine().fit(history)
    before = engine.predict("Strong", "Mid")
    assert before is not None
    # the same history plus one future match with an absurd price: predictions made before it do not change
    refit = MarketRatingEngine().fit(history)
    assert refit.predict("Strong", "Mid") == before
    extra = pd.concat([history, history.iloc[[-1]].assign(Date=history.Date.max() + pd.Timedelta(days=7), B365H=50.0, B365D=1.1, B365A=1.1)])
    assert MarketRatingEngine().fit(extra).predict("Strong", "Mid") != before   # only a played match moves the ratings
