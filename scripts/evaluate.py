"""Honest evaluation report: model vs bookmaker market, bet ROI vs claimed EV, and CLV.

Reads the ledgers and the saved training metrics; never writes them.

    python scripts/evaluate.py              # human-readable report
    python scripts/evaluate.py --json out.json
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for _p in (PROJECT_ROOT, PROJECT_ROOT / "Football", PROJECT_ROOT / "Tennis"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from sports_common.evaluation import evaluate_football_ledger, evaluate_tennis_ledger, verdict  # noqa: E402
from sports_common.jsonstore import read_json  # noqa: E402

FOOTBALL_LEDGER = PROJECT_ROOT / "Football" / "data" / "cache" / "predictions_tracker.json"
TENNIS_LEDGER = PROJECT_ROOT / "Tennis" / "data" / "tracker" / "predictions_archive.json"
FOOTBALL_METRICS = PROJECT_ROOT / "Football" / "data" / "processed" / "model_metrics.json"
TENNIS_METRICS = PROJECT_ROOT / "Tennis" / "data" / "processed" / "model_metrics.json"


def _competition_type(record: Dict[str, Any]) -> str:
    from football_core.config import LEAGUES
    info = LEAGUES.get(record.get("league") or record.get("league_key") or "", {})
    if info.get("is_international"):
        return "international"
    return "european_cup" if info.get("is_cup") else "domestic"


def _holdout_summary(metrics: Dict[str, Any], key: str) -> Dict[str, Any]:
    return {name: m[key] for name, m in sorted((metrics or {}).items()) if isinstance(m, dict) and key in m}


def build_report(project_root: Path = PROJECT_ROOT) -> Dict[str, Any]:
    football = read_json(FOOTBALL_LEDGER, default=[])
    tennis = read_json(TENNIS_LEDGER, default=[])
    fb_metrics = read_json(FOOTBALL_METRICS, default={})
    tn_metrics = read_json(TENNIS_METRICS, default={})
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "football": {
            "ledger": evaluate_football_ledger(football, competition_type=_competition_type),
            "holdout_1x2": _holdout_summary(fb_metrics, "holdout_vs_market_1x2"),
            "holdout_over25": _holdout_summary(fb_metrics, "holdout_vs_market_over25"),
        },
        "tennis": {
            "ledger": evaluate_tennis_ledger(tennis),
            "holdout": _holdout_summary(tn_metrics, "holdout_vs_market"),
        },
    }


def _fmt_bets(label: str, b: Dict[str, Any]) -> str:
    if not b.get("n"):
        return f"  {label}: no settled bets"
    line = (f"  {label}: {b['n']} bets, {b['wins']} won, staked {b['staked']:.0f}, PnL {b['pnl']:+.0f}"
            f" -> ROI {b['roi_pct']:+.1f}%")
    if b.get("claimed_ev_pct") is not None:
        line += f" (model claimed {b['claimed_ev_pct']:+.1f}% EV)"
    return line


def _fmt_holdout(rows: Dict[str, Any]) -> str:
    if not rows:
        return "  (no holdout metrics saved yet; they are written at the next retrain)"
    lines = []
    for name, m in rows.items():
        lines.append(f"  {name:<14} n={m['n']:<5} model {m['model_log_loss']:.4f} vs market {m['market_log_loss']:.4f}"
                     f"  skill {m['log_loss_skill']:+.4f}")
    return "\n".join(lines)


def render(report: Dict[str, Any]) -> str:
    fb = report["football"]["ledger"]
    tn = report["tennis"]["ledger"]
    out = [f"# Evaluation report ({report['generated_at']})", ""]

    out += ["## Football", f"Settled: {fb['settled']}, pending: {fb['pending']}", "",
            "Live 1X2 vs vig-free market: " + verdict(fb["match_odds_1x2"])]
    m = fb["match_odds_1x2"]
    if m.get("n"):
        out.append(f"  log loss model {m['model_log_loss']:.4f} vs market {m['market_log_loss']:.4f}; "
                   f"Brier {m['model_brier']:.4f} vs {m['market_brier']:.4f}")
    out.append("Live O/U 2.5 vs market: " + verdict(fb["over_under_25"]))
    out += ["", "Bets (flat 100 / Kelly on 1000 bankroll):", _fmt_bets("all (flat)", fb["bets"]),
            _fmt_bets("all (Kelly)", fb["bets"].get("kelly", {}))]
    for k, v in fb["bets_by_market"].items():
        out.append(_fmt_bets(f"market {k}", v))
    for k, v in fb["bets_by_competition"].items():
        out.append(_fmt_bets(f"{k}", v))
    clv = fb["clv"]["ev_at_close"]
    out.append(f"CLV (EV at the latest pre-match price): " +
               (f"mean {clv['mean_pct']:+.2f}% over {clv['n']} picks, {clv['share_positive_pct']:.0f}% positive"
                if clv.get("n") else "no picks with a later price yet"))
    out += ["", "Training holdout 1X2 (log loss, model vs market on the same matches):",
            _fmt_holdout(report["football"]["holdout_1x2"]), "",
            "Training holdout O/U 2.5:", _fmt_holdout(report["football"]["holdout_over25"]), ""]

    out += ["## Tennis", f"Graded: {tn['graded']}, pending: {tn['pending']}", "",
            "Live match winner vs vig-free market: " + verdict(tn["match_winner"])]
    m = tn["match_winner"]
    if m.get("n"):
        out.append(f"  log loss model {m['model_log_loss']:.4f} vs market {m['market_log_loss']:.4f}; "
                   f"Brier {m['model_brier']:.4f} vs {m['market_brier']:.4f}")
    out += ["", "Bets:", _fmt_bets("Kelly (1000 bankroll)", tn["bets"]), _fmt_bets("flat 20", tn["bets"].get("flat", {}))]
    clv = tn["clv"]["ev_at_close"]
    out.append(f"CLV (EV at the latest pre-match price): " +
               (f"mean {clv['mean_pct']:+.2f}% over {clv['n']} picks, {clv['share_positive_pct']:.0f}% positive"
                if clv.get("n") else "no picks with a later price yet"))
    out += ["", "Training holdout (log loss, model vs market):", _fmt_holdout(report["tennis"]["holdout"])]
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", type=Path, help="also write the full report as JSON to this path")
    args = parser.parse_args()
    report = build_report()
    print(render(report))
    if args.json:
        args.json.write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
