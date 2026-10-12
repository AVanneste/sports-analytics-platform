from football_core.betting.diagnostics import run_ledger_diagnostics


def bet(league, won, odds=4.0, prob=0.3):
    return {"status": "settled", "stake": 100.0, "won": won, "league": league,
            "flat_pnl": 100.0 * (odds - 1) if won else -100.0,
            "best_pick": {"odds": odds, "prob": prob, "market": "1X2", "selection": "Home"}}


def test_small_losing_cohorts_are_not_leaks_but_big_ones_are():
    small = [bet("EPL", False) for _ in range(14)]  # -100% ROI, but only 14 bets at odds 4
    d = run_ledger_diagnostics(small)
    assert d["active_leaks_count"] == 0 and "change nothing" in d["recommendations"][-1]
    big = [bet("SerieB", i % 20 == 0) for i in range(60)]  # 5% hits where the model claimed 30%
    d = run_ledger_diagnostics(big)
    leagues = {c["cohort"]: c for c in d["cohorts"]["by_league"]}
    assert leagues["SerieB"]["leak_severity"] == "HIGH_LEAK" and leagues["SerieB"]["z_score"] < -2.5
    assert d["loss_breakdown"]["structural_losses"] == round(57 - 60 * 0.7)  # 57 losses, 42 expected
