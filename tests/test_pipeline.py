"""Daily pipeline scheduling and the in-memory feature-state refresh used between weekly retrains."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from synthetic import make_football_matches, make_sackmann, make_tennis_matches

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import run_daily_pipeline as rdp  # noqa: E402


def _at(day: datetime):
    class Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return day
    return Fixed


@pytest.fixture
def tuesday(monkeypatch):
    day = datetime(2026, 10, 6, 5, 0, tzinfo=timezone.utc)
    assert day.weekday() == 1
    monkeypatch.setattr(rdp, "datetime", _at(day))
    monkeypatch.setattr(rdp, "RETRAIN_WEEKDAY", 0)
    monkeypatch.delenv("SKIP_RETRAIN", raising=False)
    monkeypatch.delenv("FORCE_RETRAIN", raising=False)
    monkeypatch.setattr(sys, "argv", ["run_daily_pipeline.py"])
    return day


def _metrics(day, schema=2, age_days=2):
    return {"schema_version": schema, "trained_at": (day - timedelta(days=age_days)).isoformat()}


def test_current_models_are_not_retrained_midweek(tuesday):
    due, why = rdp.retrain_decision({"EPL": _metrics(tuesday)}, ["EPL"], 2)
    assert due is False and "current" in why


@pytest.mark.parametrize("metrics, reason", [
    ({}, "no deployed model"),
    ({"EPL": {"schema_version": 1, "trained_at": "2026-10-05T00:00:00+00:00"}}, "older feature schema"),
    ({"EPL": {"schema_version": 2, "trained_at": "2026-09-01T00:00:00+00:00"}}, "days old"),
    ({"EPL": {"schema_version": 2}}, "timestamp"),
])
def test_missing_stale_or_outdated_models_trigger_a_retrain(tuesday, metrics, reason):
    due, why = rdp.retrain_decision(metrics, ["EPL"], 2)
    assert due is True and reason in why


def test_weekly_day_and_flags(tuesday, monkeypatch):
    fresh = {"EPL": _metrics(tuesday)}
    monkeypatch.setattr(rdp, "RETRAIN_WEEKDAY", 1)
    assert rdp.retrain_decision(fresh, ["EPL"], 2) == (True, "weekly schedule")
    monkeypatch.setattr(rdp, "RETRAIN_WEEKDAY", 0)
    monkeypatch.setenv("FORCE_RETRAIN", "1")
    assert rdp.retrain_decision(fresh, ["EPL"], 2)[0] is True
    monkeypatch.setenv("SKIP_RETRAIN", "1")
    assert rdp.retrain_decision({}, ["EPL"], 2)[0] is False  # skip wins over everything


def test_rejected_candidate_resets_the_age_clock(tuesday):
    stale_but_checked = {"EPL": {**_metrics(tuesday, age_days=30), "checked_at": (tuesday - timedelta(days=1)).isoformat()}}
    assert rdp.retrain_decision(stale_but_checked, ["EPL"], 2)[0] is False


def test_football_state_only_replay_matches_full_processing():
    from football_core.features.builder import FootballFeaturePipeline
    df = make_football_matches(seasons=2)
    full, fast = FootballFeaturePipeline("EPL"), FootballFeaturePipeline("EPL")
    full.process_historical_matches(df)
    X, y = fast.process_historical_matches(df, state_only=True)
    assert X.empty and y.empty
    assert full.elo_engine.ratings == fast.elo_engine.ratings
    assert full.dixon_coles_engine.attack_strengths == pytest.approx(fast.dixon_coles_engine.attack_strengths)
    a = full.build_inference_features("Team00", "Team03", match_date="2026-10-04")
    b = fast.build_inference_features("Team00", "Team03", match_date="2026-10-04")
    pd.testing.assert_frame_equal(a, b)


def test_tennis_state_only_replay_matches_full_processing(monkeypatch):
    from tennis_core.features import builder
    df = make_tennis_matches(n=200)
    sack = make_sackmann(df)
    monkeypatch.setattr(builder, "load_cached_sackmann", lambda circuit: sack)
    full, fast = builder.TennisFeaturePipeline("atp"), builder.TennisFeaturePipeline("atp")
    full.process_historical_matches(df)
    X, _ = fast.process_historical_matches(df, state_only=True)
    assert X.empty
    assert full.elo_engine.overall_elo == fast.elo_engine.overall_elo
    assert full.career_highs == fast.career_highs and full.sackmann_latest == fast.sackmann_latest
    a = full.build_inference_features("Player00 X.", "Player05 X.", "Hard")["features"]
    b = fast.build_inference_features("Player00 X.", "Player05 X.", "Hard")["features"]
    assert a == pytest.approx(b, nan_ok=True)


def test_refresh_state_keeps_models_and_uses_new_results():
    from football_core.features.builder import FootballFeaturePipeline
    from football_core.models.predictor import FootballPredictor
    from football_core.models.train import train_league_models
    df = make_football_matches(seasons=4)
    pipe = FootballFeaturePipeline("EPL")
    X, y = pipe.process_historical_matches(df.iloc[:-60])
    models, metrics = train_league_models(X, y, league_key="EPL")
    pred = FootballPredictor.__new__(FootballPredictor)
    pred.bundles = {"EPL": {"league_key": "EPL", "pipeline": pipe, "models": models, "metrics": metrics}}
    pred._settled_cache = None

    before = pred.bundles["EPL"]["pipeline"].elo_engine.get_rating("Team00")
    assert pred.refresh_state("EPL", df) is True
    assert pred.bundles["EPL"]["models"] is models
    assert pred.bundles["EPL"]["pipeline"].elo_engine.get_rating("Team00") != before
    assert pred.refresh_state("LaLiga", df) is False  # no deployed bundle, nothing to refresh
    res = pred.predict_match("EPL", "Team00", "Team09", match_date="2026-10-04")
    assert res["prob_home"] + res["prob_draw"] + res["prob_away"] == pytest.approx(1.0)
