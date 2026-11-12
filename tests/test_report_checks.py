import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from alerts_report import mismatch_warnings, score_calibration  # noqa: E402


def frame(sport, market, n, selection, beat, pnl=0.05):
    rng = np.random.default_rng(1)
    return pd.DataFrame({"sport": sport, "market": market, "selection": selection if isinstance(selection, list) else [selection] * n,
                         "ev_at_close": np.where(rng.random(n) < beat, 0.04, -0.03), "pnl": pnl, "edge": rng.normal(0.02, 0.03, n)})


def test_mismatch_warning_catches_one_sided_and_too_good_segments_only():
    one_sided = frame("Hockey", "total", 60, ["under"] * 55 + ["over"] * 5, 0.7)
    too_good = frame("Tennis", "spread", 50, ["home", "away"] * 25, 0.97)
    normal = frame("Soccer", "total", 80, ["over", "under"] * 40, 0.65)
    small = frame("Hockey", "spread", 10, "under", 0.99)
    warnings = mismatch_warnings(pd.concat([one_sided, too_good, normal, small]))
    assert [w.split(":")[0] for w in warnings] == ["⚠️ Hockey total", "⚠️ Tennis spread"]
    assert "mapping bug" not in warnings[0] and "probably real" in warnings[0]       # positive ROI
    assert "mapping bug" in mismatch_warnings(frame("Hockey", "total", 60, ["under"] * 58 + ["over"] * 2, 0.95, pnl=-0.1))[0]


def test_score_calibration_needs_enough_scored_alerts():
    assert score_calibration(frame("Soccer", "total", 50, "over", 0.6)) == ""
    assert "expected" in score_calibration(frame("Soccer", "total", 300, "over", 0.6))


def test_sent_mask_treats_old_rows_without_the_flag_as_sent():
    from alerts_report import sent_mask
    df = pd.DataFrame({"sent": pd.array([None, "True", "False", None], dtype="string")})
    assert sent_mask(df).tolist() == [True, True, False, True]
    assert sent_mask(pd.DataFrame({"a": [1, 2]})).tolist() == [True, True]
