"""Leakage, train/serve consistency, model promotion and model-fitting guarantees."""
import math
import warnings

import numpy as np
import pandas as pd
import pytest

from sports_common.evaluation import should_promote
from synthetic import make_football_matches, make_sackmann, make_tennis_matches


# ------------------------------------------------------------------ tennis leakage
@pytest.fixture
def tennis_with_sackmann(monkeypatch):
    from tennis_core.features import builder
    df = make_tennis_matches()
    sack = make_sackmann(df)
    monkeypatch.setattr(builder, "load_cached_sackmann", lambda circuit: sack)
    return df


def _features(X: pd.DataFrame) -> pd.DataFrame:
    from tennis_core.features.builder import FEATURE_COLUMNS
    return X[[c for c in FEATURE_COLUMNS if c in X.columns]].reset_index(drop=True)


def test_tennis_features_do_not_depend_on_future_matches(monkeypatch):
    """Truncating every data source after match k must not change any feature of matches < k."""
    from tennis_core.features import builder
    df = make_tennis_matches()
    sack = make_sackmann(df)
    monkeypatch.setattr(builder, "load_cached_sackmann", lambda circuit: sack)
    X_full, _ = builder.TennisFeaturePipeline("atp").process_historical_matches(df)

    k = 300
    cutoff = int(df.iloc[k - 1]["tourney_date"].strftime("%Y%m%d"))
    monkeypatch.setattr(builder, "load_cached_sackmann", lambda circuit: sack[sack["tourney_date"] <= cutoff])
    X_trunc, _ = builder.TennisFeaturePipeline("atp").process_historical_matches(df.iloc[:k])

    pd.testing.assert_frame_equal(_features(X_full).iloc[: 2 * k], _features(X_trunc), check_exact=False)
    # The leak-prone features are actually populated (the test would be vacuous otherwise)
    assert _features(X_full)["ace_rate_diff"].notna().sum() > 100
    assert _features(X_full)["career_high_rank_diff"].abs().sum() > 0


def test_tennis_mirror_rows_are_exact_negations(tennis_with_sackmann):
    from tennis_core.features.builder import TennisFeaturePipeline
    X, y = TennisFeaturePipeline("atp").process_historical_matches(tennis_with_sackmann.iloc[:100])
    a, b = X.iloc[0::2].reset_index(drop=True), X.iloc[1::2].reset_index(drop=True)
    assert (y.iloc[0::2] == 1).all() and (y.iloc[1::2] == 0).all()
    pd.testing.assert_series_equal(a["elo_diff"], -b["elo_diff"], check_names=False)
    pd.testing.assert_series_equal(a["log_rank_ratio"], -b["log_rank_ratio"], check_names=False)
    assert (a["p1_name"] == b["p2_name"]).all() and (a["p1_surface_exp"] == b["p2_surface_exp"]).all()
    pd.testing.assert_series_equal(a["h2h_matches"], b["h2h_matches"], check_names=False)


def test_mirror_row_rejects_unknown_features():
    from tennis_core.features.builder import mirror_row
    assert mirror_row({"p1_name": "A", "p2_name": "B", "x_diff": 2.0})["x_diff"] == -2.0
    with pytest.raises(KeyError):
        mirror_row({"p1_rank": 3})


def test_sackmann_rows_become_visible_only_after_the_lag():
    from tennis_core.data.sackmann_loader import SackmannRollingStats
    sack = pd.DataFrame([{
        "tourney_date": 20240101, "surface": "Hard", "winner_name": "A", "loser_name": "B",
        "w_ace": 7, "w_df": 1, "w_svpt": 70, "w_1stIn": 40, "w_1stWon": 30, "w_2ndWon": 15, "w_bpSaved": 2, "w_bpFaced": 4,
        "l_ace": 2, "l_df": 3, "l_svpt": 60, "l_1stIn": 35, "l_1stWon": 20, "l_2ndWon": 10, "l_bpSaved": 3, "l_bpFaced": 8,
    }])
    stats = SackmannRollingStats(sack, lag_days=14)
    stats.advance_to(pd.Timestamp("2024-01-10"))   # same tournament week: must not be visible
    assert stats.get("A", "hard") is None
    stats.advance_to(pd.Timestamp("2024-01-16"))
    a = stats.get("A", "Hard")
    assert a["ace_rate"] == pytest.approx(7 / 70) and a["return_points_won_pct"] == pytest.approx(30 / 60)


def test_paired_cv_never_splits_a_match():
    from tennis_core.models.train import paired_boundary, paired_time_series_cv
    for n in (200, 202, 999 * 2):
        assert paired_boundary(n, 0.7) % 2 == 0
        for train_idx, test_idx in paired_time_series_cv(n, 3):
            assert len(train_idx) % 2 == 0 and train_idx[-1] + 1 == test_idx[0]


def test_missing_tennis_score_records_result_without_invented_games(tennis_with_sackmann):
    from tennis_core.features.builder import TennisFeaturePipeline
    pipe = TennisFeaturePipeline("atp")
    pipe.process_historical_matches(tennis_with_sackmann.iloc[:10])
    unscored = tennis_with_sackmann.iloc[7]
    log = pipe.form_engine.player_history[unscored["winner_name"]]
    entry = [m for m in log if m["date"] == unscored["tourney_date"]][-1]
    assert entry["won"] is True and entry["games_won"] is None and entry["score"] is None


# ------------------------------------------------------------------ football
def test_football_inference_features_match_training_features():
    """Same code path: everything except the Dixon-Coles fit window must be identical."""
    from football_core.features.builder import FootballFeaturePipeline
    df = make_football_matches(seasons=2)
    X_full, _ = FootballFeaturePipeline("EPL").process_historical_matches(df)
    pipe = FootballFeaturePipeline("EPL")
    pipe.process_historical_matches(df.iloc[:-1])
    last = df.iloc[-1]
    live = pipe.build_inference_features(last["HomeTeam"], last["AwayTeam"],
                                         match_date=str(last["Date"].date()), referee=last["Referee"])
    non_dc = [c for c in X_full.columns if not c.startswith("dc_")]
    assert list(live.columns) == list(X_full.columns)
    pd.testing.assert_series_equal(live.iloc[0][non_dc], X_full.iloc[-1][non_dc], check_names=False)


def test_football_missing_stats_are_not_invented():
    from football_core.features.builder import FootballFeaturePipeline
    df = make_football_matches(seasons=1)
    df.loc[df.index[:40], ["HC", "AC", "HY", "AY"]] = np.nan
    X, y = FootballFeaturePipeline("EPL").process_historical_matches(df)
    assert y["target_corners_over95"].iloc[:40].isna().all()
    assert y["target_cards_over35"].iloc[:40].isna().all()
    assert y["target_corners_over95"].iloc[40:].notna().all()


def test_form_averages_skip_unreported_matches():
    from football_core.features.form import TeamFormTracker
    t = TeamFormTracker()
    d = pd.Timestamp("2024-01-01")
    t.record_match(d, "A", "B", 1, 0, hc=8.0, ac=2.0)
    t.record_match(d + pd.Timedelta(days=7), "A", "C", 1, 1, hc=float("nan"), ac=float("nan"))
    feats = t.get_team_rolling_features("A", d + pd.Timedelta(days=14), n_matches=5)
    assert feats["corners_for_last5"] == 8.0  # not (8 + an invented 5.2) / 2


def test_referee_engine_ignores_matches_without_card_data():
    from football_core.features.referee import RefereeStatsEngine
    e = RefereeStatsEngine()
    e.record_match("R", pd.Timestamp("2024-01-01"), yellows=None, reds=None, fouls=None)
    e.record_match("R", pd.Timestamp("2024-01-08"), yellows=6.0, reds=0.0, fouls=None)
    assert e.league_match_count == 1 and e.get_league_avg_cards() == 6.0
    assert e.get_referee_profile("R", pd.Timestamp("2024-02-01"))["matches_officiated"] == 1


def test_dixon_coles_fit_is_stable_and_sensible():
    from football_core.features.dixon_coles import DixonColesEngine
    df = make_football_matches(seasons=2)
    e = DixonColesEngine()
    e.fit_from_matches(df)
    assert e.attack_strengths["Team00"] > e.attack_strengths["Team09"]
    assert 0.0 < e.home_adv < 0.6 and -0.2 <= e.rho <= 0.1
    probs = e.predict_match_probabilities("Team00", "Team09")
    assert probs["prob_home"] > probs["prob_away"]
    assert probs["prob_home"] + probs["prob_draw"] + probs["prob_away"] == pytest.approx(1.0)

    # A promoted side that never scores in a tiny sample must not blow up (old fit overflowed)
    tiny = df.iloc[:25].copy()
    tiny.loc[tiny["HomeTeam"] == "Team09", "FTHG"] = 0
    tiny.loc[tiny["AwayTeam"] == "Team09", "FTAG"] = 0
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        e2 = DixonColesEngine()
        e2.fit_from_matches(tiny)
    assert all(np.isfinite(v) and abs(v) < 3 for v in e2.attack_strengths.values())


def test_corner_and_card_projections_are_bounded():
    from football_core.features.props import project_cards, project_corners
    c = project_corners(None, None, None, None)
    assert 8.2 <= c["expected"] <= 11.8 and c["over95"] + c["under95"] == pytest.approx(1.0)
    lenient = project_cards(2.0, 2.0, ref_strictness=0.85)
    strict = project_cards(2.0, 2.0, ref_strictness=1.25)
    assert strict["expected"] > lenient["expected"] and strict["over35"] >= lenient["over35"]


@pytest.fixture(scope="module")
def trained_league():
    from football_core.features.builder import FootballFeaturePipeline
    from football_core.models.train import train_league_models
    df = make_football_matches(seasons=4)
    pipe = FootballFeaturePipeline("EPL")
    X, y = pipe.process_historical_matches(df)
    models, metrics = train_league_models(X, y, league_key="EPL")
    return pipe, models, metrics, X


def test_train_league_models_reports_untouched_test_window_and_refits(trained_league, monkeypatch):
    from football_core.models import train as train_mod
    _, models, metrics, X = trained_league
    assert metrics["n_train"] + metrics["n_validation"] + metrics["n_test"] == len(X)
    assert set(metrics["blend_weights"]) == {"ml_1x2", "ml_over25", "ml_btts"}
    assert metrics["holdout_vs_market_1x2"]["n"] == metrics["n_test"]
    assert metrics["schema_version"] == 2
    assert set(models) == {"model_1x2", "model_over25", "model_btts", "base_1x2"}
    assert models["base_1x2"].n_features_in_ == X.shape[1]

    sizes = []
    real = train_mod.fit_outcome_models
    monkeypatch.setattr(train_mod, "fit_outcome_models", lambda Xf, yf: sizes.append(len(Xf)) or real(Xf, yf))
    _, y = trained_league[0], None
    train_mod.train_league_models(X, pd.DataFrame({
        "target_1x2": np.resize([0, 1, 2], len(X)), "target_over25": np.resize([0, 1], len(X)),
        "target_btts": np.resize([1, 0], len(X)), "Date": pd.Timestamp("2024-01-01"),
    }), league_key="EPL")
    assert sizes == [int(len(X) * 0.70), len(X)]  # fit on the training window, then refit on everything


def test_predictor_accepts_iso_string_dates(trained_league):
    """Regression: string fixture dates crashed every domestic prediction in the daily pipeline."""
    from football_core.models.predictor import FootballPredictor
    pipe, models, metrics, _ = trained_league
    predictor = FootballPredictor.__new__(FootballPredictor)
    predictor.bundles = {"EPL": {"league_key": "EPL", "pipeline": pipe, "models": models, "metrics": metrics}}
    predictor._settled_cache = None
    for date in ("2026-10-04", "2026-10-04T14:00:00Z", None):
        res = predictor.predict_match("EPL", "Team00", "Team05", match_date=date,
                                      odds_home=1.8, odds_draw=3.6, odds_away=4.5)
        assert res["prob_home"] + res["prob_draw"] + res["prob_away"] == pytest.approx(1.0)
        assert 8.0 <= res["expected_corners"] <= 12.0


# ------------------------------------------------------------------ promotion gate
def _m(skill, ll=0.98, schema=2):
    return {"schema_version": schema, "holdout_vs_market_1x2": {"model_log_loss": ll, "log_loss_skill": skill}}


def test_promotion_gate_rules():
    key, cap = "holdout_vs_market_1x2", math.log(3)
    assert should_promote(_m(0.02), None, key, 2, cap)[0] is True                 # nothing deployed
    assert should_promote(_m(0.02), _m(0.01, schema=1), key, 2, cap)[0] is True   # old schema
    assert should_promote(_m(0.012), _m(0.010), key, 2, cap)[0] is True           # within tolerance
    assert should_promote(_m(0.030), _m(0.010), key, 2, cap)[0] is False          # clearly worse
    assert should_promote(_m(0.0, ll=1.2), None, key, 2, cap)[0] is False         # worse than uninformed
    assert should_promote({}, _m(0.01), key, 2, cap)[0] is False


def test_retrain_league_keeps_deployed_models_but_refreshes_state(tmp_path, monkeypatch, trained_league):
    from football_core.models import train as train_mod
    monkeypatch.setattr(train_mod, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(train_mod, "METRICS_FILE", tmp_path / "metrics.json")
    pipe, models, metrics, _ = trained_league
    excellent = dict(metrics, holdout_vs_market_1x2=dict(metrics["holdout_vs_market_1x2"], log_loss_skill=-0.5))
    train_mod.save_trained_bundle(pipe, models, excellent, "EPL")

    df = make_football_matches(seasons=4, seed=11)
    res = train_mod.retrain_league("EPL", df)
    assert res["status"] == "kept_current"
    bundle = train_mod.load_trained_bundle("EPL")
    assert bundle["metrics"]["holdout_vs_market_1x2"]["log_loss_skill"] == -0.5
    assert "rejected_candidate" in bundle["metrics"]
    assert bundle["pipeline"] is not pipe  # feature state rebuilt from the new data
