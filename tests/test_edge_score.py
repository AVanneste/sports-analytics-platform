import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from sports_common.edge_score import MIN_SEGMENT, closed_frame, fit, predict, validate

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from odds_alerts import plan_alerts  # noqa: E402


def archive_rows(n=900, seed=0):
    """Two segments: tennis games totals close well above their claimed EV, soccer moneylines well below."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        tennis = i % 2 == 0
        day = 1 + (i * 28) // n
        ev = float(rng.uniform(0.02, 0.10))
        rows.append({"captured_at": f"2026-10-{day:02d}T10:00:00Z", "start": f"2026-10-{day:02d}T13:00:00Z",
                     "sport": "Tennis" if tennis else "Soccer", "market": "total" if tennis else "moneyline",
                     "units": "Games" if tennis else "", "period": "0", "ev": ev, "limit": 300, "dropped_from": "",
                     "ev_at_close": float(0.5 * ev + (0.03 if tennis else -0.04) + rng.normal(0, 0.03)), "price": 1.9})
    return rows


def test_fit_predict_ranks_segments_and_mutes_unproven_ones():
    df = closed_frame(archive_rows())
    model = fit(df)
    test = closed_frame(archive_rows(200, seed=1))
    odd = test.iloc[[0]].assign(sport="Hockey", market="total", units="", period=0)  # a segment the model never saw
    both = pd.concat([test, odd], ignore_index=True)
    score = predict(model, both)
    assert score[both["sport"] == "Tennis"].mean() > 0.02 > score[both["sport"] == "Soccer"].mean()
    assert np.isnan(score.iloc[-1]) and MIN_SEGMENT > 1


def test_validate_publishes_a_useful_model_and_refuses_noise():
    assert validate(closed_frame(archive_rows()))["ok"] is True
    noise = archive_rows(seed=3)
    rng = np.random.default_rng(9)
    for r in noise: r["ev_at_close"] = float(rng.normal(0, 0.03))  # closing value unrelated to anything
    assert validate(closed_frame(noise))["ok"] is False


def test_with_a_model_only_proven_alerts_above_min_edge_are_sent_but_all_are_collected():
    file = json.loads((ROOT / "alerts_settings.json").read_text())
    collect, settings = file["collect"], {**{k: v for k, v in file.items() if k != "collect"}, "min_ev_pct": 3.0, "min_edge_pct": 3.0, "books": ["napoleon"]}
    model = fit(closed_frame(archive_rows()))
    now = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
    base = {"market": "total", "period": 0, "units": "Games", "side": None, "line": 20.5, "selection": "over", "start": "2026-10-30T14:00:00Z",
            "stake": 0.01, "book": "napoleon", "price": 1.9, "ev": 0.06, "sport": "Tennis", "limit": 300}
    soccer = {**base, "event_id": 2, "market": "moneyline", "units": None, "sport": "Soccer", "line": None, "selection": "home"}
    sent, rows = plan_alerts([{**base, "event_id": 1}, soccer], {}, {}, collect, settings, now, min_ev=0.03, model=model)
    assert [(a["sport"], round(a["edge"], 2) > 0.03) for a in sent] == [("Tennis", True)]
    assert {(r["sport"], r["sent"]) for r in rows} == {("Tennis", True), ("Soccer", False)}
    assert 0 < sent[0]["stake"] < 0.05                                    # quarter-Kelly on the expected edge
    assert next(r for r in rows if r["sport"] == "Soccer")["edge"] < 0.0   # collected with its (negative) score


def test_hockey_rows_from_before_the_overtime_fix_never_train_the_score():
    rows = archive_rows(20)
    fake = {**rows[0], "sport": "Hockey", "market": "total", "units": "", "period": "6", "captured_at": "2026-11-05T10:00:00Z", "start": "2026-11-05T13:00:00Z"}
    real = {**fake, "captured_at": "2026-11-12T10:00:00Z", "start": "2026-11-12T13:00:00Z"}
    kept = closed_frame(rows + [fake, real])
    assert (kept["sport"] == "Hockey").sum() == 1 and kept[kept["sport"] == "Hockey"].iloc[0]["captured_at"].startswith("2026-11-12")
