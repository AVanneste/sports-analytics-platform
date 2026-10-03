"""Walk-forward accuracy backtest for the football models.

    python scripts/backtest.py                                  # all domestic leagues, seasons 2022/23 onwards
    python scripts/backtest.py --leagues EPL LaLiga --models base_rate dixon_coles
    python scripts/backtest.py --from 2023-07-01 --json report.json

Lower is better for every loss column. Bookmaker rows (market_open / market_close) are a yardstick
only: no model uses odds as an input.
"""
import argparse
import json
import logging
from pathlib import Path

from football_core.config import LEAGUES
from football_core.models.backtest import BASELINES, run_backtest

DOMESTIC = [k for k, v in LEAGUES.items() if not v.get("is_cup") and not v.get("is_international")]


def _fmt(metrics: dict, market: str, key: str) -> str:
    value = metrics.get(market, {}).get(key)
    return f"{value:.4f}" if isinstance(value, float) else "   -  "


def render(block: dict, reference: str, title: str) -> str:
    lines = [f"\n## {title} ({block['matches']} matches)",
             f"{'model':<22}{'1X2 LL':>8}{'RPS':>8}{'acc':>8}{'ECE':>8}{'O2.5 LL':>9}{'BTTS LL':>9}{'score LL':>9}"
             f"{'C9.5 LL':>9}{'K3.5 LL':>9}   Δ1X2 LL vs {reference}"]
    for name, metrics in block["models"].items():
        diff = block["vs_reference"].get(name, {}).get("1x2")
        delta = f"{diff['mean']:+.4f} ± {diff['se']:.4f}" if diff else ""
        lines.append(f"{name:<22}{_fmt(metrics, '1x2', 'log_loss'):>8}{_fmt(metrics, '1x2', 'rps'):>8}"
                     f"{_fmt(metrics, '1x2', 'accuracy'):>8}{_fmt(metrics, '1x2', 'ece'):>8}"
                     f"{_fmt(metrics, 'over25', 'log_loss'):>9}{_fmt(metrics, 'btts', 'log_loss'):>9}"
                     f"{_fmt(metrics, 'score', 'log_loss'):>9}{_fmt(metrics, 'corners_over95', 'log_loss'):>9}"
                     f"{_fmt(metrics, 'cards_over35', 'log_loss'):>9}   {delta}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--leagues", nargs="+", default=DOMESTIC)
    parser.add_argument("--models", nargs="+", default=list(BASELINES), choices=list(BASELINES))
    parser.add_argument("--from", dest="eval_from", default="2022-07-01")
    parser.add_argument("--to", dest="eval_to", default=None)
    parser.add_argument("--reference", default="dixon_coles")
    parser.add_argument("--workers", type=int, help="leagues evaluated in parallel (default: all at once)")
    parser.add_argument("--json", type=Path, help="write the full report here")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    for noisy in ("football_core", "lightgbm"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("football_core.models.backtest").setLevel(logging.INFO)

    report = run_backtest(args.leagues, lambda: [BASELINES[name]() for name in args.models], args.eval_from,
                          args.eval_to, reference=args.reference, workers=args.workers)
    for lk, block in report["leagues"].items():
        print(render(block, args.reference, lk))
    print(render(report["pooled"], args.reference, "ALL LEAGUES"))
    if args.json:
        args.json.write_text(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
