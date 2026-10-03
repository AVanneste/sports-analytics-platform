"""Walk-forward accuracy backtest for the tennis match-winner models.

    python scripts/backtest_tennis.py                                   # ATP + WTA, July 2024 onwards
    python scripts/backtest_tennis.py --circuits atp --models rank elo --start-year 2014
    python scripts/backtest_tennis.py --json report.json

``--start-year`` is the first season the ratings and features are built from (the deployed models
use tennis_core.config.START_YEAR). Lower is better for log loss, Brier and calibration error.
Bookmaker rows (market_pinnacle / market_bet365) are a yardstick only.
"""
import argparse
import json
import logging
from functools import partial
from pathlib import Path

from tennis_core.config import START_YEAR
from tennis_core.models.backtest import EloRatingModel, ProductionModel, SymmetricLogit, run_backtest

MODELS = {
    "rank": partial(SymmetricLogit, "rank", ["log_rank_ratio"]),
    "elo_features": partial(SymmetricLogit, "elo_features", ["elo_diff", "effective_surface_elo_diff"]),
    "elo": partial(EloRatingModel, "elo"),
    "production": ProductionModel,
}


def render(block: dict, reference: str, title: str) -> str:
    lines = [f"\n## {title} ({block['matches']} matches)",
             f"{'model':<18}{'log loss':>9}{'Brier':>8}{'acc':>8}{'ECE':>8}   Δ log loss vs {reference}"]
    for name, m in block["models"].items():
        if not m:
            continue
        diff = block["vs_reference"].get(name)
        delta = f"{diff['mean']:+.4f} ± {diff['se']:.4f} (n={diff['n']})" if diff else ""
        lines.append(f"{name:<18}{m['log_loss']:>9.4f}{m['brier']:>8.4f}{m['accuracy']:>8.4f}{m['ece']:>8.4f}   {delta}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--circuits", nargs="+", default=["atp", "wta"])
    parser.add_argument("--models", nargs="+", default=list(MODELS), choices=list(MODELS))
    parser.add_argument("--from", dest="eval_from", default="2024-07-01")
    parser.add_argument("--to", dest="eval_to", default=None)
    parser.add_argument("--start-year", type=int, default=START_YEAR)
    parser.add_argument("--reference", default="elo")
    parser.add_argument("--json", type=Path, help="write the full report here")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(message)s")
    logging.getLogger("tennis_core.models.backtest").setLevel(logging.INFO)

    report = run_backtest(args.circuits, lambda: [MODELS[m]() for m in args.models], args.eval_from,
                          args.eval_to, start_year=args.start_year, reference=args.reference)
    for circuit, block in report["circuits"].items():
        print(render(block, args.reference, circuit.upper()))
    print(render(report["pooled"], args.reference, "BOTH TOURS"))
    if args.json:
        args.json.write_text(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
