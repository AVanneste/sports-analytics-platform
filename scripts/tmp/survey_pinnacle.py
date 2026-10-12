"""Temporary: print Pinnacle's market structure for new sports (run on a GitHub runner)."""
import collections

from sports_common.pinnacle import parse_board, pinnacle_get

sports = {s["name"]: s["id"] for s in pinnacle_get("sports")}
print({k: sports.get(k) for k in ("Hockey", "Volleyball", "Handball")})
for name in ("Hockey", "Volleyball", "Handball"):
    m, p = pinnacle_get(f"sports/{sports[name]}/matchups"), pinnacle_get(f"sports/{sports[name]}/markets/straight")
    rows = parse_board(m, p)
    print(f"\n== {name}: {len({r['event_id'] for r in rows})} games")
    for k, n in collections.Counter((r["units"], r["market"], r["period"]) for r in rows if not r["alternate"]).most_common(12):
        print("   ", n, k)
    mu = [x for x in m if x.get("type") == "matchup"]
    print("   units:", collections.Counter(x.get("units") for x in mu))
    print("   moneyline p0 selections:", collections.Counter(r["selection"] for r in rows if r["market"] == "moneyline" and r["period"] == 0))
    ex = next((r for r in rows if r["market"] == "total" and r["period"] == 0 and not r["units"]), None)
    print("   sample main total:", ex and (ex["home"], ex["away"], ex["line"]))
    ex = next((r for r in rows if r["market"] == "spread" and r["period"] == 0 and not r["units"]), None)
    print("   sample main spread:", ex and (ex["home"], ex["line"]))
