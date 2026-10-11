"""Weekly scouting refresh (run by .github/workflows/scout_weekly.yml): FotMob stats -> scores -> web/public/data/scout.json.

    python scripts/update_scout.py [--skip-fetch] [--max-age 26] [--limit 1500]

Fetches every scouting league's season stats and squads (football_core/data/fotmob_players.py,
about 30 minutes), scores them (football_core/scouting.py), adds foot and contract end for the
exported shortlist (profiles cached 30 days in data/processed/scout/profiles.parquet) and writes
the Scout tab's payload. ``--skip-fetch`` rescores the last fetched table.
"""
import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from football_core import scouting
from football_core.data.fotmob_players import SCOUT_DIR, add_profiles, update_scout

OUT = Path(__file__).resolve().parent.parent / "web" / "public" / "data" / "scout.json"
PROFILES = SCOUT_DIR / "profiles.parquet"
PROFILE_DAYS = 30


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--max-age", type=float, default=26)
    parser.add_argument("--limit", type=int, default=1500)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    players = pd.read_parquet(SCOUT_DIR / "players.parquet") if args.skip_fetch else update_scout()
    scored = scouting.score(players)
    shortlist = scored[scored["age"] <= args.max_age].nlargest(args.limit, "adj_score")[["player_id"]]
    known = pd.read_parquet(PROFILES) if PROFILES.exists() else None
    if known is not None:
        known = known[pd.to_datetime(known["fetched_at"], utc=True) > pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=PROFILE_DAYS)]
    profiles = add_profiles(shortlist, known)
    profiles["fetched_at"] = profiles.get("fetched_at", pd.Series(index=profiles.index, dtype=object)).fillna(
        datetime.now(timezone.utc).isoformat(timespec="seconds"))
    profiles.to_parquet(PROFILES, index=False)
    scored = scored.merge(profiles[["player_id", "foot", "contract_end"]], on="player_id", how="left")

    payload = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               **scouting.export(scored, max_age=args.max_age, limit=args.limit)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    logging.info(f"{len(payload['players'])} players of {payload['pool_size']} scored -> {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
