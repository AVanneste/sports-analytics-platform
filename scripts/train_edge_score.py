"""Train the expected-edge score on the closed alerts of the last 60 days (run weekly by alerts_weekly.yml).

    python scripts/train_edge_score.py --archive odds_archive [--days 60] [--dry-run]

Reads ``<archive>/snapshots/alerts/*.csv`` (every collected alert, sent or not), validates on the latest
10 days (sports_common/edge_score.validate) and, only if the top half of the holdout beats the bottom
half by a clear margin, writes ``<archive>/edge_model.json`` for scripts/odds_alerts.py. Otherwise the
previous model stays.
"""
import argparse
import csv
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sports_common.edge_score import closed_frame, fit, validate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--archive", type=Path, required=True, help="the odds-archive checkout")
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    since = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")
    rows = []
    for path in sorted((args.archive / "snapshots" / "alerts").glob("*.csv")):
        if path.stem >= since:
            with open(path, newline="", encoding="utf-8") as fh:
                rows += list(csv.DictReader(fh))
    df = closed_frame(rows)
    logging.info(f"{len(df)} closed alerts since {since}")
    check = validate(df) if len(df) else {"ok": False, "reason": "no alerts"}
    logging.info(f"validation: {json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in check.items()})}")
    if not check["ok"]:
        logging.info("Not published: the previous model stays.")
        return
    model = {**fit(df), "validation": check, "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    logging.info(f"model: {model['trained_on']} alerts, {len(model['segments'])} segments, "
                 f"{sum(v >= 100 for v in model['segments'].values())} proven")
    if not args.dry_run:
        (args.archive / "edge_model.json").write_text(json.dumps(model, indent=1))


if __name__ == "__main__":
    main()
