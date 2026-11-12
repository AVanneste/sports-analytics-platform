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


def sent_mask(df: pd.DataFrame) -> pd.Series:
    """True for alerts that were sent: anything except an explicit False (rows from before the column existed were all sent)."""
    return df["sent"].fillna("True").astype(str).ne("False") if "sent" in df else pd.Series(True, index=df.index)


def load(days: int, include_unsent: bool = False) -> pd.DataFrame:
    """Closed alerts of the last ``days`` days with their real result (``pnl`` per unit staked,
    NaN while unsettled or for player props) from snapshots/alert_results/."""
    subprocess.run(["git", "fetch", "-q", "origin", "odds-archive"], check=True)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    alerts, results = _read(FOLDER, since), _read("snapshots/alert_results", since)
    if alerts.empty:
        return alerts
    if not include_unsent:  # rows collected for learning but not sent to the user stay out of the numbers
        alerts = alerts[sent_mask(alerts)]
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


def mismatch_warnings(df: pd.DataFrame, min_alerts: int = 40) -> list:
    """Segments that look like a mapping bug, not an edge: 40+ alerts where one side is over 85% of them or
    over 92% beat the close (Napoleon's hockey overtime markets read as regulation looked exactly like this)."""
    out = []
    for (sport, market), g in df.groupby(["sport", "market"]):
        if len(g) < min_alerts:
            continue
        side = g["selection"].value_counts(normalize=True)
        beat = (g["ev_at_close"] > 0).mean()
        if side.iloc[0] > 0.85 or beat > 0.92:
            roi = g["pnl"].mean()
            verdict = ("likely a mapping bug: it beats the close but loses money" if roi < 0
                       else "unusually strong and it pays in real results: probably real softness, keep watching")
            out.append(f"⚠️ {sport} {market}: {len(g)} alerts, {side.index[0]} is {100 * side.iloc[0]:.0f}% of them, "
                       f"{100 * beat:.0f}% beat the close, ROI {100 * roi:+.1f}% ({verdict})")
    return out


def score_calibration(df: pd.DataFrame) -> str:
    """Expected edge against actual closing value by fifth, for the alerts that carry a score."""
    if "edge" not in df or df["edge"].notna().sum() < 100:
        return ""
    s = df[df["edge"].notna()]
    t = s.groupby(pd.qcut(s["edge"], 5, duplicates="drop")).agg(alerts=("edge", "size"), expected=("edge", lambda x: 100 * x.mean()),
                                                                 actual_close=("ev_at_close", lambda x: 100 * x.mean()))
    return "Score calibration (expected edge vs closing value, %):\n" + t.round(2).to_string(index=False)


def price_lifetime(df: pd.DataFrame) -> str:
    """How fast alerted prices disappear, by sport: the share gone by the next run (polled every 5
    minutes) says whether polling faster would catch more of them."""
    if "gone_after" not in df:
        return ""
    gone = pd.to_numeric(df["gone_after"], errors="coerce")
    tracked = df.assign(gone=gone)[df["captured_at"] >= "2026-11-13"]  # gone_after recorded from then on
    if len(tracked) < 50:
        return ""
    t = tracked.groupby("sport").agg(alerts=("gone", "size"), gone_by_next_run=("gone", lambda g: 100 * (g <= 7).mean()),
                                     gone_within_30m=("gone", lambda g: 100 * (g <= 30).mean()),
                                     lasted_to_kickoff=("gone", lambda g: 100 * g.isna().mean()))
    return "Price lifetime (% of alerts):\n" + t.round(0).to_string()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--telegram", action="store_true", help="also send the report to Telegram")
    parser.add_argument("--all-candidates", action="store_true", help="include alerts collected for learning but not sent")
    args = parser.parse_args()
    everything = load(args.days, include_unsent=True)
    everything = everything[everything["ev_at_close"].notna()] if not everything.empty else everything
    df = everything if args.all_candidates else everything[sent_mask(everything)]
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
        if (~sent_mask(everything)).any():  # what the user's filters leave out
            both = everything.assign(sent=sent_mask(everything).map({True: "sent", False: "not sent"}))
            lines.append("Collected for learning vs sent to you:\n" + summary(both, "sent").to_string())
        if (calibration := score_calibration(everything)):
            lines.append(calibration)
        if (lifetime := price_lifetime(everything)):
            lines.append(lifetime)
        lines += mismatch_warnings(everything)
    print("\n\n".join(lines))
    if args.telegram:
        from sports_common.notify import send
        send(lines)


if __name__ == "__main__":
    main()
