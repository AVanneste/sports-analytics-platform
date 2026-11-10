"""How the +EV alerts did against Pinnacle's closing price (CLV), from the odds-archive branch.

    python scripts/alerts_report.py [--days 30] [--telegram]

Reads ``snapshots/alerts/*.csv`` (written by scripts/odds_alerts.py) from ``origin/odds-archive``
after a fetch. "EV at close" is the alert price against Pinnacle's last fair price before kick-off:
consistently above 0 means the alerts beat the closing line. "ROI" is the real flat-stake return on
the alerts settled so far (scripts/settle_alerts.py; player props are not settled).
"""
import argparse
import io
import subprocess
from datetime import datetime, timedelta, timezone

import pandas as pd

BRANCH, FOLDER = "origin/odds-archive", "snapshots/alerts"


KEY = ["captured_at", "sport", "start", "home", "away", "market", "period", "units", "side", "line", "selection", "book"]


def _read(folder: str, since: str) -> pd.DataFrame:
    names = subprocess.run(["git", "ls-tree", "--name-only", f"{BRANCH}:{folder}"], capture_output=True, text=True).stdout.split()
    frames = [pd.read_csv(io.StringIO(subprocess.run(["git", "show", f"{BRANCH}:{folder}/{n}"], capture_output=True,
                                                     text=True, check=True).stdout))
              for n in names if n.endswith(".csv") and n[:10] >= since]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _keyed(df: pd.DataFrame) -> pd.DataFrame:
    """Key columns as comparable text ("2.0" and "2" alike, blanks for missing)."""
    df = df.copy()
    for k in KEY:
        df[k] = df[k].astype(object).where(df[k].notna(), "").astype(str).str.replace(r"\.0$", "", regex=True)
    return df


def load(days: int) -> pd.DataFrame:
    """Closed alerts of the last ``days`` days with their real result (``pnl`` per unit staked,
    NaN while unsettled or for player props) from snapshots/alert_results/."""
    subprocess.run(["git", "fetch", "-q", "origin", "odds-archive"], check=True)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    alerts, results = _read(FOLDER, since), _read("snapshots/alert_results", since)
    if alerts.empty:
        return alerts
    if results.empty:
        return alerts.assign(pnl=float("nan"))
    return _keyed(alerts).merge(_keyed(results)[KEY + ["result", "pnl"]].drop_duplicates(KEY), on=KEY, how="left")


def summary(df: pd.DataFrame, by=None) -> pd.DataFrame:
    """Alerts, mean EV when sent and at the close, share that beat the close, and the real return
    on the settled ones (flat stakes)."""
    stats = lambda g: pd.Series({"alerts": len(g), "ev_sent_%": 100 * g["ev"].mean(),
                                 "ev_close_%": 100 * g["ev_at_close"].mean(),
                                 "beat_close_%": 100 * (g["ev_at_close"] > 0).mean(),
                                 "settled": g["pnl"].notna().sum(), "roi_%": 100 * g["pnl"].mean()})
    return (df.groupby(by).apply(stats) if by else stats(df).to_frame("all").T).round(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--telegram", action="store_true", help="also send the report to Telegram")
    args = parser.parse_args()
    df = load(args.days)
    df = df[df["ev_at_close"].notna()] if not df.empty else df
    if df.empty:
        lines = [f"Alerts report ({args.days} days): no closed alerts yet."]
    else:
        df["market"] = df["market"] + df["units"].fillna("").astype(str).map(lambda u: f" ({u.lower()})" if u else "")
        df["kind"] = df["dropped_from"].notna().map({True: "drop", False: "ev"})
        overall = summary(df).iloc[0]
        lines = [f"📊 Alerts, last {args.days} days: {overall['alerts']:.0f} closed · EV sent {overall['ev_sent_%']:+.1f}% · "
                 f"EV at close {overall['ev_close_%']:+.1f}% · beat the close {overall['beat_close_%']:.0f}% · "
                 f"real ROI {overall['roi_%']:+.1f}% on {overall['settled']:.0f} settled"]
        for by in ("sport", "market", "book", "kind"):
            lines.append(summary(df, by).sort_values("alerts", ascending=False).to_string())
    print("\n\n".join(lines))
    if args.telegram:
        from sports_common.notify import send
        send(lines)


if __name__ == "__main__":
    main()
