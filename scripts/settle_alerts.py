"""Settle sent alerts against real results (hourly, from .github/workflows/odds_collector.yml).

    python scripts/settle_alerts.py --archive odds_archive/snapshots [--days 3]

Reads the alerts of the last ``--days`` capture days (snapshots/alerts/<day>.csv), settles those
not settled yet whose game started over 3 hours ago (sports_common/settle.py: Napoleon's finished
events) and writes snapshots/alert_results/<day>.csv. Only this script writes those files.
"""
import argparse
import csv
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sports_common.settle import KEY, RESULT_COLUMNS, finished_events, settle_alerts


def read(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def key(row: dict) -> tuple:
    return tuple(str(row.get(k) or "") for k in KEY)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--archive", type=Path, required=True, help="the odds-archive checkout's snapshots folder")
    parser.add_argument("--days", type=int, default=3)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    now = datetime.now(timezone.utc)
    days = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(args.days + 1)]
    done = {d: read(args.archive / "alert_results" / f"{d}.csv") for d in days}
    settled = {key(r) for rows in done.values() for r in rows}
    cutoff = (now - timedelta(hours=3)).isoformat()
    todo = []
    for d in days:
        for a in read(args.archive / "alerts" / f"{d}.csv"):
            if key(a) not in settled and a["start"].replace("Z", "+00:00") < cutoff and a["market"] != "player_prop":
                a["line"] = float(a["line"]) if a.get("line") not in (None, "") else None
                a["period"] = int(float(a.get("period") or 0))
                todo.append({**a, "day": d})
    if not todo:
        logging.info("Nothing to settle.")
        return
    parse = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    first, last = min(parse(a["start"]) for a in todo), max(parse(a["start"]) for a in todo)
    events = finished_events(first - timedelta(hours=13), last + timedelta(hours=13))
    rows = settle_alerts(todo, events)
    day_of = {key(a): a["day"] for a in todo}
    for r in rows:
        done[day_of[key(r)]].append(r)
    out = args.archive / "alert_results"
    out.mkdir(parents=True, exist_ok=True)
    for d, day_rows in done.items():
        if day_rows:
            with open(out / f"{d}.csv", "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(RESULT_COLUMNS), extrasaction="ignore")
                writer.writeheader()
                writer.writerows(day_rows)
    logging.info(f"{len(rows)} of {len(todo)} alerts settled ({len(events)} finished events read)")


if __name__ == "__main__":
    main()
